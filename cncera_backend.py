#!/usr/bin/env python3
"""
CNCera Backend - Unified Application
AI-Powered CNC Analysis & G-code Generation Backend
Все в одном файле для простого развертывания
"""

import os
import sys
import json
import hashlib
import logging
import subprocess
import base64
import shutil
import tempfile
import math
import time
import re
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Union
from datetime import datetime
from string import Template

# Flask imports
from flask import Flask, request, jsonify, send_from_directory, send_file, Blueprint
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

# Optional imports with fallbacks
try:
    import openai
except ImportError:
    openai = None

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
except ImportError:
    matplotlib = None
    plt = None

try:
    from stl import mesh as stlmesh
except ImportError:
    stlmesh = None

# ==================== CONFIGURATION ====================

class Config:
    """Application Configuration"""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Directories
    BASE_DIR = Path(__file__).parent.resolve()
    TEMP_FOLDER = BASE_DIR / 'temp'
    MODELS_FOLDER = BASE_DIR / 'models'
    STATIC_FOLDER = BASE_DIR / 'static'
    
    # File upload limits
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS = {'.step', '.stp', '.stl'}
    
    # FreeCAD settings
    FREECAD_CMD = None
    FREECAD_TIMEOUT = 600  # 10 minutes
    
    # OpenAI settings
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    
    # CAM settings
    MAX_CAM_POINTS = 40000
    DEFAULT_TOOL_DIAMETER = 3.0
    DEFAULT_FEED_RATE = 300.0
    DEFAULT_SPINDLE_SPEED = 8000
    
    def __init__(self):
        self.FREECAD_CMD = self._locate_freecad()
        
        # Create directories
        for directory in [self.TEMP_FOLDER, self.MODELS_FOLDER, self.STATIC_FOLDER]:
            directory.mkdir(parents=True, exist_ok=True)
    
    def _locate_freecad(self):
        """Locate FreeCADCmd executable"""
        # Check environment variables
        for key in ("FREECADCMD_PATH", "FREECADCMD"):
            val = os.environ.get(key)
            if val and os.path.isfile(val):
                return val
        
        # Check PATH
        for name in ("FreeCADCmd.exe", "FreeCADCmd"):
            path = shutil.which(name)
            if path:
                return path
        
        # Standard paths
        patterns = [
            r"C:/Program Files/FreeCAD*/bin/FreeCADCmd*.exe",
            r"C:/Program Files (x86)/FreeCAD*/bin/FreeCADCmd*.exe",
            "/usr/bin/FreeCADCmd",
            "/usr/local/bin/FreeCADCmd",
            "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd"
        ]
        
        import glob
        for pattern in patterns:
            matches = glob.glob(pattern)
            for match in matches:
                if os.path.isfile(match):
                    return match
        
        return None

# ==================== UTILITIES ====================

def validate_float(value: Union[str, float, int], default: float, min_val: float, max_val: float) -> float:
    """Validate and constrain float values"""
    try:
        val = float(value)
        return max(min_val, min(max_val, val))
    except (TypeError, ValueError):
        return default

def validate_int(value: Union[str, int, float], default: int, min_val: int, max_val: int) -> int:
    """Validate and constrain int values"""
    try:
        val = int(value)
        return max(min_val, min(max_val, val))
    except (TypeError, ValueError):
        return default

def validate_string(value: Union[str, None], default: str, allowed_values: Optional[list] = None) -> str:
    """Validate string values"""
    if not isinstance(value, str):
        return default
    
    if allowed_values and value not in allowed_values:
        return default
    
    return value

def allowed_file(filename: str, allowed_extensions: set) -> bool:
    """Check if file extension is allowed"""
    return Path(filename).suffix.lower() in allowed_extensions

def get_uploaded_size(fs) -> int:
    """Safely determine uploaded file size"""
    try:
        cl = getattr(fs, "content_length", None)
        if isinstance(cl, int) and cl >= 0:
            return cl
    except Exception:
        pass
    
    try:
        stream = getattr(fs, "stream", None)
        if stream is not None and hasattr(stream, "tell") and hasattr(stream, "seek"):
            pos = stream.tell()
            stream.seek(0, 2)  # SEEK_END
            size = stream.tell()
            stream.seek(pos, 0)  # SEEK_SET back
            if isinstance(size, int) and size >= 0:
                return size
    except Exception:
        pass
    
    try:
        hdr = request.headers.get("Content-Length")
        if hdr is not None:
            return int(hdr)
    except Exception:
        pass
    
    return 0

def generate_file_hash(file_path: Path) -> str:
    """Generate file hash"""
    return hashlib.md5(str(file_path).encode()).hexdigest()

def cleanup_temp_files(*file_paths: Path) -> None:
    """Cleanup temporary files"""
    for path in file_paths:
        try:
            if path and path.exists():
                path.unlink()
        except Exception:
            pass

# ==================== SERVICES ====================

class AiService:
    """AI Service for OpenAI integration"""
    
    def __init__(self, config):
        self.config = config
        self.api_key = config.OPENAI_API_KEY
        self.chat_sessions = {}
        
        if self.api_key and openai:
            openai.api_key = self.api_key
    
    def is_available(self) -> bool:
        """Check if AI service is available"""
        return bool(self.api_key and openai)
    
    def chat(self, message: str, session_id: str, context: Optional[Dict] = None) -> str:
        """Chat with AI consultant"""
        if not self.is_available():
            return "ИИ сервис недоступен. Проверьте настройку OPENAI_API_KEY."
        
        try:
            # Initialize session
            if session_id not in self.chat_sessions:
                self.chat_sessions[session_id] = []
            
            # Add context if provided
            context_info = ""
            if context:
                dimensions = context.get("geometry", {}).get("dimensions", {})
                if dimensions:
                    context_info = f"\nТекущая деталь: {dimensions.get('length', 0):.1f} x {dimensions.get('width', 0):.1f} x {dimensions.get('height', 0):.1f} мм"
            
            # Build conversation history
            messages = [
                {
                    "role": "system", 
                    "content": f"Вы эксперт по CNC обработке. Помогайте с техническими вопросами по программированию ЧПУ, инструментам и производству. Отвечайте на русском языке.{context_info}"
                }
            ]
            
            # Add recent chat history (last 10 messages)
            for msg in self.chat_sessions[session_id][-10:]:
                messages.append(msg)
            
            # Add current message
            messages.append({"role": "user", "content": message})
            
            # Request to OpenAI
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
            
            # Store in session history
            self.chat_sessions[session_id].append({"role": "user", "content": message})
            self.chat_sessions[session_id].append({"role": "assistant", "content": ai_response})
            
            # Limit history to last 20 messages
            if len(self.chat_sessions[session_id]) > 20:
                self.chat_sessions[session_id] = self.chat_sessions[session_id][-20:]
            
            return ai_response
            
        except Exception as e:
            return f"Извините, произошла ошибка: {str(e)}"
    
    def analyze_part(self, stl_path: Path, part_info: Dict) -> Dict:
        """AI part analysis"""
        if not self.is_available():
            return {"error": "ИИ сервис недоступен"}
        
        try:
            dimensions = part_info.get("geometry", {}).get("dimensions", {})
            mesh_info = part_info.get("mesh_info", {})
            
            analysis_prompt = f"""
            Проанализируйте эту 3D деталь для CNC обработки:
            
            Размеры: {dimensions.get('length', 0):.1f} x {dimensions.get('width', 0):.1f} x {dimensions.get('height', 0):.1f} мм
            Сложность сетки: {mesh_info.get('vertices', 0)} вершин, {mesh_info.get('faces', 0)} граней
            
            Предоставьте рекомендации по:
            1. Стратегии обработки (черновая, чистовая и т.д.)
            2. Рекомендуемые размеры и типы инструментов
            3. Оптимальные параметры резания (подачи, скорости)
            4. Рекомендации по закреплению заготовки
            5. Потенциальные проблемы и их решения
            6. Примерное время обработки
            
            Ответьте в формате JSON со структурированными разделами.
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Вы эксперт-инженер по CNC обработке. Предоставьте детальный технический анализ."},
                    {"role": "user", "content": analysis_prompt}
                ],
                max_tokens=1500,
                temperature=0.3
            )
            
            ai_analysis = response.choices[0].message.content
            
            # Try to parse as JSON, fallback to text
            try:
                return json.loads(ai_analysis)
            except:
                return {"analysis": ai_analysis}
                
        except Exception as e:
            return {"error": f"Ошибка ИИ анализа: {str(e)}"}
    
    def generate_gcode_params(self, stl_path: Path, part_info: Dict, requirements: str) -> Dict:
        """AI G-code parameter generation"""
        if not self.is_available():
            return {"error": "ИИ сервис недоступен"}
        
        try:
            dimensions = part_info.get("geometry", {}).get("dimensions", {})
            
            gcode_prompt = f"""
            Сгенерируйте оптимальные параметры CNC для этой детали:
            
            Размеры детали: {dimensions.get('length', 0):.1f} x {dimensions.get('width', 0):.1f} x {dimensions.get('height', 0):.1f} мм
            Требования: {requirements}
            
            Предоставьте JSON с параметрами:
            {{
                "tool_diameter": <мм>,
                "spindle_speed": <об/мин>,
                "feed_rate": <мм/мин>,
                "plunge_rate": <мм/мин>,
                "stepover": <0.1-0.8>,
                "stepdown": <мм>,
                "operation_type": "milling|roughing|finishing",
                "controller": "fanuc|siemens|heidenhain",
                "strategy": "описание стратегии обработки",
                "estimated_time": "примерное время"
            }}
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Вы эксперт по программированию ЧПУ. Генерируйте оптимальные параметры обработки."},
                    {"role": "user", "content": gcode_prompt}
                ],
                max_tokens=800,
                temperature=0.2
            )
            
            ai_params = response.choices[0].message.content
            
            # Try to parse JSON
            try:
                return json.loads(ai_params)
            except:
                # Extract parameters using regex
                params = {}
                patterns = {
                    "tool_diameter": r'"tool_diameter":\s*(\d+\.?\d*)',
                    "spindle_speed": r'"spindle_speed":\s*(\d+)',
                    "feed_rate": r'"feed_rate":\s*(\d+\.?\d*)',
                    "plunge_rate": r'"plunge_rate":\s*(\d+\.?\d*)',
                    "stepover": r'"stepover":\s*(\d+\.?\d*)',
                    "stepdown": r'"stepdown":\s*(\d+\.?\d*)',
                    "operation_type": r'"operation_type":\s*"([^"]*)"',
                    "controller": r'"controller":\s*"([^"]*)"'
                }
                
                for key, pattern in patterns.items():
                    match = re.search(pattern, ai_params)
                    if match:
                        try:
                            if key in ["tool_diameter", "feed_rate", "plunge_rate", "stepover", "stepdown"]:
                                params[key] = float(match.group(1))
                            elif key == "spindle_speed":
                                params[key] = int(match.group(1))
                            else:
                                params[key] = match.group(1)
                        except:
                            pass
                
                params["raw_response"] = ai_params
                return params
                
        except Exception as e:
            return {"error": f"Ошибка генерации параметров: {str(e)}"}

class StlService:
    """STL file analysis and rendering service"""
    
    def analyze_stl(self, stl_path: Path) -> Dict:
        """Analyze STL file"""
        if not stlmesh:
            return {"vertices": 0, "faces": 0, "error": "numpy-stl не установлен"}
        
        try:
            mesh = stlmesh.Mesh.from_file(str(stl_path))
            return {
                "vertices": len(mesh.vectors) * 3,
                "faces": len(mesh.vectors),
                "volume": mesh.volume if hasattr(mesh, 'volume') else 0,
                "surface_area": mesh.areas.sum() if hasattr(mesh, 'areas') else 0
            }
        except Exception as e:
            return {"vertices": 0, "faces": 0, "error": f"Ошибка анализа STL: {str(e)}"}
    
    def render_stl_to_png(self, stl_path: Path, png_path: Path) -> bool:
        """Render STL to PNG"""
        if not matplotlib or not stlmesh or not plt:
            return False
        
        try:
            mesh = stlmesh.Mesh.from_file(str(stl_path))
            faces = mesh.vectors
            
            # Calculate center and radius
            xs, ys, zs = mesh.x, mesh.y, mesh.z
            cx = (xs.min() + xs.max()) / 2
            cy = (ys.min() + ys.max()) / 2
            cz = (zs.min() + zs.max()) / 2
            
            r = max(
                (xs.max() - xs.min()) / 2,
                (ys.max() - ys.min()) / 2,
                (zs.max() - zs.min()) / 2
            ) or 1.0
            
            # Create figure
            fig = plt.figure(figsize=(8, 8), dpi=150)
            ax = fig.add_subplot(111, projection="3d")
            
            # Setup colors
            fig.patch.set_facecolor("#0b1b24")
            ax.set_facecolor("#0b1b24")
            ax.set_proj_type("ortho")
            
            # Add mesh
            collection = Poly3DCollection(faces, linewidths=0.1)
            collection.set_facecolor((0.55, 0.75, 0.95, 1.0))
            collection.set_edgecolor((0.1, 0.1, 0.15, 0.25))
            ax.add_collection3d(collection)
            
            # Setup axes
            ax.set_xlim(cx - r, cx + r)
            ax.set_ylim(cy - r, cy + r)
            ax.set_zlim(cz - r, cz + r)
            ax.set_axis_off()
            ax.view_init(30, 45)
            
            # Save
            fig.tight_layout(pad=0)
            fig.savefig(
                str(png_path), 
                transparent=False, 
                facecolor=fig.get_facecolor(),
                bbox_inches='tight',
                dpi=150
            )
            plt.close(fig)
            
            return True
            
        except Exception as e:
            try:
                plt.close("all")
            except:
                pass
            return False

class FreecadService:
    """FreeCAD STEP to STL conversion service"""
    
    def __init__(self, config):
        self.config = config
        self.freecad_cmd = config.FREECAD_CMD
        self.timeout = config.FREECAD_TIMEOUT
    
    def is_available(self) -> bool:
        """Check if FreeCAD is available"""
        return bool(self.freecad_cmd and os.path.isfile(self.freecad_cmd))
    
    def convert_step_to_stl(self, 
                          step_path: Path, 
                          stl_path: Path,
                          linear_deflection: float = 0.1,
                          angular_deflection: float = 15.0,
                          relative: bool = False,
                          units: str = "auto") -> Dict:
        """Convert STEP to STL"""
        
        if not self.is_available():
            raise FileNotFoundError("FreeCADCmd не найден. Установите FreeCAD или укажите FREECADCMD_PATH")
        
        # Create directory for STL
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Temporary files
        sys_tmp = Path(tempfile.gettempdir())
        script_hash = hashlib.md5(str(step_path).encode()).hexdigest()
        tmp_py = sys_tmp / f"fc_{script_hash}.py"
        out_json = sys_tmp / f"fc_{script_hash}_result.json"
        
        try:
            # Prepare parameters
            lin = validate_float(linear_deflection, 0.1, 0.01, 10.0)
            ang = validate_float(angular_deflection, 15.0, 0.01, 89.0)
            rel = "True" if relative else "False"
            units = units.lower() if units in ("auto", "mm", "inch", "m") else "auto"
            
            # Create FreeCAD script
            script_content = self._create_conversion_script(
                step_path, stl_path, out_json, lin, ang, rel, units
            )
            
            tmp_py.write_text(script_content, encoding="utf-8")
            
            # Execute FreeCAD
            result = self._execute_freecad(tmp_py)
            
            # Read result
            if not out_json.exists():
                raise RuntimeError(f"FreeCAD не создал файл результата: {result}")
            
            result_data = json.loads(out_json.read_text(encoding="utf-8"))
            
            if not result_data.get("success", False):
                raise RuntimeError(f"FreeCAD ошибка: {result_data.get('error', 'неизвестная ошибка')}")
            
            return result_data
            
        finally:
            # Cleanup temporary files
            cleanup_temp_files(tmp_py, out_json)
    
    def _create_conversion_script(self, step_path: Path, stl_path: Path, json_path: Path,
                                lin: float, ang: float, rel: str, units: str) -> str:
        """Create FreeCAD conversion script"""
        
        # Normalize paths for different OS
        sp = str(step_path).replace("\\", "/")
        tp = str(stl_path).replace("\\", "/")
        jp = str(json_path).replace("\\", "/")
        
        script_template = """
import os, sys, json, traceback, math
import FreeCAD as App
import Part, Mesh, MeshPart

# Parameters
step_path = r"$STEP_PATH"
stl_path = r"$STL_PATH"
json_path = r"$JSON_PATH"
linear_deflection = $LINEAR_DEFLECTION
angular_deflection_deg = $ANGULAR_DEFLECTION
relative = $RELATIVE
units = "$UNITS"

def write_result(result_dict):
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"JSON write error: {e}")

try:
    # Create document
    doc = App.newDocument("conversion_doc")
    
    # Import STEP file
    import Import
    Import.insert(step_path, "conversion_doc")
    
    # Get objects
    objects = doc.Objects
    if not objects:
        raise Exception("STEP file contains no objects")
    
    # Filter objects with geometry
    shape_objects = [obj for obj in objects if hasattr(obj, 'Shape') and obj.Shape is not None]
    if not shape_objects:
        raise Exception("No objects with geometry found")
    
    # Combine geometry
    if len(shape_objects) == 1:
        combined_shape = shape_objects[0].Shape
    else:
        combined_shape = shape_objects[0].Shape
        for obj in shape_objects[1:]:
            try:
                combined_shape = combined_shape.fuse(obj.Shape)
            except Exception as fuse_error:
                # If fuse fails, create compound
                try:
                    shapes = [combined_shape] + [obj.Shape for obj in shape_objects[1:]]
                    combined_shape = Part.makeCompound(shapes)
                    break
                except Exception as compound_error:
                    print(f"Combine error: fuse={fuse_error}, compound={compound_error}")
                    pass
    
    # Scale if needed
    scale_factors = {"inch": 25.4, "m": 1000.0, "mm": 1.0, "auto": 1.0}
    scale = scale_factors.get(units, 1.0)
    
    if abs(scale - 1.0) > 1e-9:
        matrix = App.Matrix()
        matrix.A11 = scale
        matrix.A22 = scale
        matrix.A33 = scale
        combined_shape = combined_shape.transformGeometry(matrix)
    
    # Get bounding box
    bbox = combined_shape.BoundBox
    
    # Create mesh
    try:
        mesh_obj = MeshPart.meshFromShape(
            Shape=combined_shape,
            LinearDeflection=linear_deflection,
            AngularDeflection=math.radians(angular_deflection_deg),
            Relative=relative
        )
        
        # Save STL
        mesh_obj.write(stl_path)
        
        # Prepare result
        result = {
            "success": True,
            "error": "",
            "file_info": {
                "filename": os.path.basename(step_path),
                "file_type": ".step",
                "file_size": os.path.getsize(step_path)
            },
            "geometry": {
                "dimensions": {
                    "length": round(bbox.XLength, 3),
                    "width": round(bbox.YLength, 3),
                    "height": round(bbox.ZLength, 3)
                },
                "units": "mm",
                "bounding_box": {
                    "min": [round(bbox.XMin, 3), round(bbox.YMin, 3), round(bbox.ZMin, 3)],
                    "max": [round(bbox.XMax, 3), round(bbox.YMax, 3), round(bbox.ZMax, 3)],
                    "center": [
                        round((bbox.XMin + bbox.XMax) / 2.0, 3),
                        round((bbox.YMin + bbox.YMax) / 2.0, 3),
                        round((bbox.ZMin + bbox.ZMax) / 2.0, 3)
                    ]
                }
            },
            "conversion_settings": {
                "LinearDeflection": linear_deflection,
                "AngularDeflection_deg": angular_deflection_deg,
                "Relative": relative,
                "Units": units,
                "Scale": scale
            },
            "mesh_info": {
                "faces": len(mesh_obj.Facets) if hasattr(mesh_obj, 'Facets') else 0,
                "points": len(mesh_obj.Points) if hasattr(mesh_obj, 'Points') else 0
            }
        }
        
        write_result(result)
        print("Conversion completed successfully")
        
    except Exception as mesh_error:
        error_result = {
            "success": False,
            "error": f"Mesh creation error: {str(mesh_error)}",
            "traceback": traceback.format_exc()
        }
        write_result(error_result)
        print(f"Mesh error: {mesh_error}")
        
except Exception as main_error:
    error_result = {
        "success": False,
        "error": f"General error: {str(main_error)}",
        "traceback": traceback.format_exc()
    }
    write_result(error_result)
    print(f"General error: {main_error}")
    traceback.print_exc()
"""
        
        return Template(script_template).substitute(
            STEP_PATH=sp,
            STL_PATH=tp,
            JSON_PATH=jp,
            LINEAR_DEFLECTION=lin,
            ANGULAR_DEFLECTION=ang,
            RELATIVE=rel,
            UNITS=units
        )
    
    def _execute_freecad(self, script_path: Path) -> str:
        """Execute FreeCAD script"""
        
        # Process settings
        creationflags = 0x08000000 if os.name == "nt" else 0
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        
        try:
            process = subprocess.run(
                [self.freecad_cmd, str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
                creationflags=creationflags,
                env=env,
                text=True
            )
            
            if process.returncode != 0:
                error_msg = f"FreeCAD exited with code {process.returncode}"
                if process.stderr:
                    error_msg += f"\nSTDERR: {process.stderr[-500:]}"
                if process.stdout:
                    error_msg += f"\nSTDOUT: {process.stdout[-500:]}"
                raise RuntimeError(error_msg)
            
            return process.stdout
            
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"FreeCAD timeout {self.timeout} seconds")
        except FileNotFoundError:
            raise RuntimeError(f"FreeCAD not found at: {self.freecad_cmd}")

# ==================== G-CODE GENERATION ====================

def get_controller_settings(controller: str) -> Dict:
    """Get controller-specific G-code settings"""
    settings = {
        "fanuc": {
            "header": ["G90", "G17", "G21", "G54"],
            "spindle_on": "M3 S{spindle}",
            "spindle_off": "M5",
            "coolant_on": "M8",
            "coolant_off": "M9",
            "rapid": "G0",
            "linear": "G1",
            "program_end": "M30"
        },
        "siemens": {
            "header": ["G90", "G17", "G71", "G54"],
            "spindle_on": "M3 S{spindle}",
            "spindle_off": "M5",
            "coolant_on": "M7",
            "coolant_off": "M9",
            "rapid": "G0",
            "linear": "G1",
            "program_end": "M2"
        },
        "heidenhain": {
            "header": ["* - Generated by CNCera", "BLK FORM 0.1 Z X+0 Y+0 Z-50"],
            "spindle_on": "SPINDLE ON CW SPEED {spindle}",
            "spindle_off": "SPINDLE OFF",
            "coolant_on": "COOLANT ON",
            "coolant_off": "COOLANT OFF",
            "rapid": "L",
            "linear": "L",
            "program_end": "END PGM"
        },
        "gsk": {
            "header": ["G90", "G17", "G21", "G54"],
            "spindle_on": "M3 S{spindle}",
            "spindle_off": "M5",
            "coolant_on": "M8",
            "coolant_off": "M9",
            "rapid": "G00",
            "linear": "G01",
            "program_end": "M30"
        },
        "mazak": {
            "header": ["G90", "G17", "G21", "G54"],
            "spindle_on": "M3 S{spindle}",
            "spindle_off": "M5",
            "coolant_on": "M8",
            "coolant_off": "M9",
            "rapid": "G0",
            "linear": "G1",
            "program_end": "M99"
        }
    }
    return settings.get(controller, settings["fanuc"])

def build_top_sampler(stl_path: Path, step_xy: float):
    """Build STL top surface sampler for CAM"""
    if stlmesh is None:
        raise RuntimeError("numpy-stl not installed")
    
    m = stlmesh.Mesh.from_file(str(stl_path))
    tris = m.vectors
    xs, ys, zs = m.x, m.y, m.z
    xmin, xmax = float(xs.min()), float(xs.max())
    ymin, ymax = float(ys.min()), float(ys.max())
    zmin, zmax = float(zs.min()), float(zs.max())
    
    # Simple grid-based sampling for this unified version
    def z_func(px: float, py: float) -> Optional[float]:
        # Find the highest Z value at this XY position
        best_z = None
        for tri in tris:
            # Simple point-in-triangle test and Z interpolation
            # This is a simplified version - full implementation would be more complex
            (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = tri
            
            # Check if point is roughly within triangle bounds
            tri_xmin, tri_xmax = min(x1, x2, x3), max(x1, x2, x3)
            tri_ymin, tri_ymax = min(y1, y2, y3), max(y1, y2, y3)
            
            if (tri_xmin <= px <= tri_xmax and tri_ymin <= py <= tri_ymax):
                # Simple Z interpolation (not accurate but functional)
                z_avg = (z1 + z2 + z3) / 3
                if best_z is None or z_avg > best_z:
                    best_z = z_avg
        
        return best_z
    
    return (xmin, xmax, ymin, ymax, zmin, zmax), z_func

def generate_raster_gcode(stl_path: Path, out_path: Path, **params) -> Dict:
    """Generate raster G-code"""
    
    # Validate parameters
    tool_diam = validate_float(params.get('tool_diam', 3.0), 3.0, 0.1, 50.0)
    stepover = validate_float(params.get('stepover', 0.4), 0.4, 0.05, 0.95)
    feed = validate_float(params.get('feed', 300.0), 300.0, 10.0, 5000.0)
    plunge = validate_float(params.get('plunge', 120.0), 120.0, 10.0, 2000.0)
    clearance = validate_float(params.get('clearance', 5.0), 5.0, 1.0, 50.0)
    spindle = validate_int(params.get('spindle', 8000), 8000, 1000, 24000) if params.get('spindle') else None
    controller = validate_string(params.get('controller', 'fanuc'), 'fanuc', 
                                ['fanuc', 'siemens', 'heidenhain', 'gsk', 'mazak'])
    operation_type = validate_string(params.get('operation_type', 'milling'), 'milling')
    
    # Get geometry bounds
    step_xy = max(0.1, tool_diam * stepover)
    (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler(stl_path, step_xy)
    
    # Apply allowances
    allowance_x = validate_float(params.get('allowance_x', 0.0), 0.0, -10.0, 10.0)
    allowance_y = validate_float(params.get('allowance_y', 0.0), 0.0, -10.0, 10.0)
    allowance_z = validate_float(params.get('allowance_z', 0.0), 0.0, -10.0, 10.0)
    
    xmin -= allowance_x
    xmax += allowance_x
    ymin -= allowance_y
    ymax += allowance_y
    zmax += allowance_z
    
    # Calculate grid
    nx = max(2, int(math.ceil((xmax - xmin) / step_xy)) + 1)
    ny = max(2, int(math.ceil((ymax - ymin) / step_xy)) + 1)
    
    # Origin setup
    origin = validate_string(params.get('origin', 'bbox_min'), 'bbox_min', 
                           ['bbox_min', 'bbox_center', 'bbox_top_center'])
    ox, oy, oz = {
        "bbox_min": (xmin, ymin, zmin),
        "bbox_center": ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0, zmin),
        "bbox_top_center": ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0, zmax)
    }[origin]
    
    # Controller settings
    controller_settings = get_controller_settings(controller)
    
    # Generate toolpath
    def zigzag_lines():
        lines = []
        dir_axis = validate_string(params.get('dir_axis', 'X'), 'X', ['X', 'Y'])
        
        if dir_axis == "X":
            ys = [ymin + i * step_xy for i in range(ny)]
            for j, y in enumerate(ys):
                xs = [xmin + i * step_xy for i in range(nx)]
                if j % 2 == 1:
                    xs.reverse()
                lines.append([(x, y) for x in xs])
        else:
            xs = [xmin + i * step_xy for i in range(nx)]
            for i, x in enumerate(xs):
                ys = [ymin + j * step_xy for j in range(ny)]
                if i % 2 == 1:
                    ys.reverse()
                lines.append([(x, y) for y in ys])
        return lines
    
    # Write G-code
    with open(out_path, "w", encoding="ascii", errors="ignore") as f:
        w = f.write
        w(f"(Generated by CNCera - {operation_type.title()} - {controller.upper()})\n")
        w(f"(Origin: {origin})\n")
        
        # Header
        for cmd in controller_settings["header"]:
            w(f"{cmd}\n")
        
        if spindle:
            w(f"{controller_settings['spindle_on'].format(spindle=spindle)}\n")
        w(f"{controller_settings['coolant_on']}\n")
        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
        
        # Main toolpath
        w("(Main toolpath)\n")
        for line in zigzag_lines():
            x0, y0 = line[0]
            w(f"{controller_settings['rapid']} X{(x0 - ox):.3f} Y{(y0 - oy):.3f}\n")
            
            z0 = z_func(x0, y0)
            if z0 is not None:
                w(f"{controller_settings['linear']} Z{(z0 - oz):.3f} F{plunge:.1f}\n")
                w(f"F{feed:.1f}\n")
            else:
                w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
            
            for x, y in line[1:]:
                z = z_func(x, y)
                if z is None:
                    w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
                    w(f"{controller_settings['rapid']} X{(x - ox):.3f} Y{(y - oy):.3f}\n")
                else:
                    w(f"{controller_settings['linear']} X{(x - ox):.3f} Y{(y - oy):.3f} Z{(z - oz):.3f}\n")
        
        # Footer
        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
        w(f"{controller_settings['coolant_off']}\n")
        if spindle:
            w(f"{controller_settings['spindle_off']}\n")
        w(f"{controller_settings['program_end']}\n")
    
    return {
        "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin, "zmax": zmax},
        "grid": {"nx": nx, "ny": ny, "step_xy": step_xy},
        "origin": {"ox": ox, "oy": oy, "oz": oz}
    }

# ==================== FLASK APPLICATION ====================

def create_app():
    """Create Flask application"""
    
    app = Flask(__name__)
    config = Config()
    
    # Configure Flask
    app.config.from_object(config)
    
    # Setup CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8080"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
    
    # Middleware
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    # Logging setup
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    # Services
    ai_service = AiService(config)
    stl_service = StlService()
    freecad_service = FreecadService(config)
    
    # Global error handler
    @app.errorhandler(Exception)
    def handle_error(e):
        app.logger.error("Uncaught exception: %s", e, exc_info=True)
        return jsonify({
            "success": False,
            "error": f"Internal server error: {str(e)}"
        }), 500
    
    # ==================== ROUTES ====================
    
    @app.route('/api/health')
    def health_check():
        return jsonify({
            "status": "ok",
            "service": "CNCera Backend API",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat()
        })
    
    @app.route('/api/info')
    def api_info():
        return jsonify({
            "name": "CNCera Backend API",
            "version": "1.0.0",
            "features": {
                "ai_chat": ai_service.is_available(),
                "ai_analysis": ai_service.is_available(),
                "freecad_conversion": freecad_service.is_available(),
                "supported_formats": [".step", ".stp", ".stl"],
                "supported_controllers": ["fanuc", "siemens", "heidenhain", "gsk", "mazak"]
            },
            "limits": {
                "max_file_size": config.MAX_CONTENT_LENGTH,
                "max_cam_points": config.MAX_CAM_POINTS
            }
        })
    
    @app.route('/api/upload', methods=['POST'])
    def upload_file():
        """Upload and analyze file"""
        disk_path = None
        
        try:
            # Validate request
            if 'file' not in request.files:
                return jsonify({"success": False, "error": "Файл не предоставлен"}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({"success": False, "error": "Файл не выбран"}), 400
            
            if not allowed_file(file.filename, config.ALLOWED_EXTENSIONS):
                return jsonify({
                    "success": False, 
                    "error": "Поддерживаются только форматы: .step, .stp, .stl"
                }), 400
            
            # Check file size
            file_size = get_uploaded_size(file)
            if config.MAX_CONTENT_LENGTH and file_size > config.MAX_CONTENT_LENGTH:
                return jsonify({
                    "success": False, 
                    "error": f"Файл слишком большой (макс. {config.MAX_CONTENT_LENGTH // (1024*1024)} МБ)"
                }), 400
            
            # Save file
            filename = secure_filename(file.filename)
            disk_path = config.TEMP_FOLDER / filename
            file.save(str(disk_path))
            
            # Get processing parameters
            units = request.form.get('units', 'auto').lower()
            linear_deflection = validate_float(request.form.get('linear_deflection', 0.1), 0.1, 0.01, 10.0)
            angular_deflection = validate_float(request.form.get('angular_deflection_deg', 15), 15.0, 0.01, 89.0)
            relative = request.form.get('relative', 'false').lower() in ('1', 'true', 'yes', 'on')
            
            # Process file
            ext = disk_path.suffix.lower()
            stl_name = generate_file_hash(disk_path) + '.stl'
            stl_path = config.MODELS_FOLDER / stl_name
            
            if ext in ('.step', '.stp'):
                # Convert STEP to STL
                result = freecad_service.convert_step_to_stl(
                    disk_path, stl_path, linear_deflection, angular_deflection, relative, units
                )
            elif ext == '.stl':
                # Copy STL file
                shutil.copyfile(str(disk_path), str(stl_path))
                result = {
                    "success": True,
                    "file_info": {
                        "filename": filename,
                        "file_type": ".stl",
                        "file_size": disk_path.stat().st_size
                    },
                    "geometry": {
                        "dimensions": {"length": 0, "width": 0, "height": 0},
                        "units": "mm"
                    }
                }
            else:
                return jsonify({"success": False, "error": "Неподдерживаемый тип файла"}), 400
            
            # Analyze STL
            mesh_info = stl_service.analyze_stl(stl_path)
            result['mesh_info'] = mesh_info
            
            # Generate preview
            png_path = config.MODELS_FOLDER / (stl_name.replace('.stl', '.png'))
            stl_service.render_stl_to_png(stl_path, png_path)
            
            # Prepare response
            result.update({
                "model_path": f"/api/models/{stl_name}",
                "preview_png": f"/api/models/{png_path.name}" if png_path.exists() else None
            })
            
            # Save result
            result_name = f"result_{generate_file_hash(disk_path)}.json"
            result_path = config.TEMP_FOLDER / result_name
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            result['result_filename'] = result_name
            
            app.logger.info(f"File processed successfully: {filename}")
            return jsonify(result)
            
        except Exception as e:
            app.logger.error(f"Upload failed: {e}", exc_info=True)
            return jsonify({
                "success": False, 
                "error": f"Ошибка обработки файла: {str(e)}"
            }), 500
            
        finally:
            cleanup_temp_files(disk_path)
    
    @app.route('/api/ai/chat', methods=['POST'])
    def ai_chat():
        """AI chat consultant"""
        try:
            data = request.get_json() or {}
            message = data.get('message', '').strip()
            session_id = data.get('session_id', 'default')
            context = data.get('context')
            
            if not message:
                return jsonify({"success": False, "error": "Сообщение не может быть пустым"}), 400
            
            if not ai_service.is_available():
                return jsonify({
                    "success": False, 
                    "error": "ИИ сервис недоступен. Проверьте настройку OPENAI_API_KEY"
                }), 503
            
            response = ai_service.chat(message, session_id, context)
            
            return jsonify({
                "success": True,
                "response": response,
                "session_id": session_id
            })
            
        except Exception as e:
            app.logger.error(f"AI chat error: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500
    
    @app.route('/api/ai/analyze', methods=['POST'])
    def ai_analyze():
        """AI part analysis"""
        try:
            data = request.get_json() or {}
            model_path = data.get('model_path', '')
            
            if not model_path or not model_path.startswith('/api/models/'):
                return jsonify({"success": False, "error": "Некорректный путь к модели"}), 400
            
            model_filename = Path(model_path).name
            stl_path = config.MODELS_FOLDER / model_filename
            
            if not stl_path.exists():
                return jsonify({"success": False, "error": "STL файл не найден"}), 404
            
            if not ai_service.is_available():
                return jsonify({
                    "success": False, 
                    "error": "ИИ сервис недоступен. Проверьте настройку OPENAI_API_KEY"
                }), 503
            
            # Get part info
            part_info = get_part_info(model_path, config)
            
            # AI analysis
            analysis = ai_service.analyze_part(stl_path, part_info)
            
            return jsonify({
                "success": True,
                "analysis": analysis,
                "part_info": part_info
            })
            
        except Exception as e:
            app.logger.error(f"AI analysis error: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500
    
    @app.route('/api/ai/generate-params', methods=['POST'])
    def ai_generate_params():
        """AI G-code parameter generation"""
        try:
            data = request.get_json() or {}
            model_path = data.get('model_path', '')
            requirements = data.get('requirements', '')
            
            if not model_path or not model_path.startswith('/api/models/'):
                return jsonify({"success": False, "error": "Некорректный путь к модели"}), 400
            
            model_filename = Path(model_path).name
            stl_path = config.MODELS_FOLDER / model_filename
            
            if not stl_path.exists():
                return jsonify({"success": False, "error": "STL файл не найден"}), 404
            
            if not ai_service.is_available():
                return jsonify({
                    "success": False, 
                    "error": "ИИ сервис недоступен. Проверьте настройку OPENAI_API_KEY"
                }), 503
            
            # Get part info
            part_info = get_part_info(model_path, config)
            
            # Generate parameters
            params = ai_service.generate_gcode_params(stl_path, part_info, requirements)
            
            return jsonify({
                "success": True,
                "parameters": params
            })
            
        except Exception as e:
            app.logger.error(f"AI parameter generation error: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500
    
    @app.route('/api/gcode/generate', methods=['POST'])
    def generate_gcode():
        """Generate G-code"""
        try:
            data = request.get_json() or {}
            model_path = data.get('model_path', '')
            
            if not model_path or not model_path.startswith('/api/models/'):
                return jsonify({"success": False, "error": "Некорректный путь к модели"}), 400
            
            model_filename = Path(model_path).name
            stl_path = config.MODELS_FOLDER / model_filename
            
            if not stl_path.exists():
                return jsonify({"success": False, "error": "STL файл не найден"}), 404
            
            # Generate G-code filename
            controller = validate_string(data.get('controller', 'fanuc'), 'fanuc')
            operation = validate_string(data.get('operation_type', 'milling'), 'milling')
            gcode_filename = f"gcode_{controller}_{operation}_{stl_path.stem}.nc"
            gcode_path = config.TEMP_FOLDER / gcode_filename
            
            # Generate G-code
            result = generate_raster_gcode(stl_path, gcode_path, **data)
            
            return jsonify({
                "success": True,
                "gcode_filename": gcode_filename,
                "download_url": f"/api/files/gcode/{gcode_filename}",
                "metadata": result,
                "controller": controller,
                "operation": operation
            })
            
        except Exception as e:
            app.logger.error(f"G-code generation failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500
    
    @app.route('/api/models/<filename>')
    def serve_model(filename):
        """Serve STL models and PNG previews"""
        try:
            file_path = config.MODELS_FOLDER / filename
            
            if not file_path.exists():
                return jsonify({"error": "Файл не найден"}), 404
            
            # Determine MIME type
            ext = file_path.suffix.lower()
            mime_types = {
                '.stl': 'model/stl',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg'
            }
            
            mimetype = mime_types.get(ext, 'application/octet-stream')
            
            return send_file(
                str(file_path),
                mimetype=mimetype,
                as_attachment=False,
                download_name=filename
            )
            
        except Exception as e:
            app.logger.error(f"Error serving model file {filename}: {e}")
            return jsonify({"error": "Ошибка при отдаче файла"}), 500
    
    @app.route('/api/files/gcode/<filename>')
    def download_gcode(filename):
        """Download G-code"""
        try:
            file_path = config.TEMP_FOLDER / filename
            
            if not file_path.exists():
                return jsonify({"error": "G-код файл не найден"}), 404
            
            return send_file(
                str(file_path),
                mimetype='text/plain',
                as_attachment=True,
                download_name=filename
            )
            
        except Exception as e:
            app.logger.error(f"Error downloading G-code {filename}: {e}")
            return jsonify({"error": "Ошибка при скачивании G-кода"}), 500
    
    @app.route('/api/files/results/<filename>')
    def download_result(filename):
        """Download analysis results"""
        try:
            file_path = config.TEMP_FOLDER / filename
            
            if not file_path.exists():
                return jsonify({"error": "Файл результата не найден"}), 404
            
            return send_file(
                str(file_path),
                mimetype='application/json',
                as_attachment=True,
                download_name=filename
            )
            
        except Exception as e:
            app.logger.error(f"Error downloading result {filename}: {e}")
            return jsonify({"error": "Ошибка при скачивании результата"}), 500
    
    return app

def get_part_info(model_path: str, config) -> dict:
    """Get part info from stored results"""
    temp_folder = config.TEMP_FOLDER
    
    # Search for corresponding result file
    for result_file in temp_folder.glob('result_*.json'):
        try:
            result_data = json.loads(result_file.read_text(encoding='utf-8'))
            if result_data.get('model_path') == model_path:
                return result_data
        except Exception:
            continue
    
    # If not found, create basic info
    model_filename = Path(model_path).name
    stl_path = config.MODELS_FOLDER / model_filename
    
    if stl_path.exists():
        stl_service = StlService()
        mesh_info = stl_service.analyze_stl(stl_path)
        return {
            "geometry": {"dimensions": {"length": 0, "width": 0, "height": 0}},
            "mesh_info": mesh_info
        }
    
    return {
        "geometry": {"dimensions": {"length": 0, "width": 0, "height": 0}},
        "mesh_info": {"vertices": 0, "faces": 0}
    }

# ==================== MAIN ====================

if __name__ == '__main__':
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    # Create app
    app = create_app()
    
    # Configuration
    host = os.getenv('BACKEND_HOST', '127.0.0.1')
    port = int(os.getenv('BACKEND_PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    print("🚀 CNCera Backend API - Unified Version")
    print(f"   Server: http://{host}:{port}")
    print(f"   API Info: http://{host}:{port}/api/info")
    print(f"   Health: http://{host}:{port}/api/health")
    print(f"   Debug: {debug}")
    
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  OpenAI API key not set - AI features will be disabled")
    
    # Run server
    app.run(
        host=host,
        port=port,
        debug=debug,
        use_reloader=False
    )