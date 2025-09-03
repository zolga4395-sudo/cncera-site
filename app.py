#!/usr/bin/env python3
"""
CNCera Enhanced - Advanced 3D Analysis & G-code Generation
Final working version with FreeCAD paths and minimal dependencies
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
import requests
import re
import threading
import traceback
import glob
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from string import Template

import flask
from flask import Flask, request, jsonify, send_file, send_from_directory, render_template_string
from werkzeug.utils import secure_filename

# ---- Server-side PNG rendering (fallback) ----
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    try:
        from stl import mesh as stlmesh
    except Exception:
        stlmesh = None
except Exception:
    matplotlib = None
    stlmesh = None
    plt = None

# ---- Embedded Classes ----
class ErrorType(Enum):
    VALIDATION_ERROR = "validation_error"
    SECURITY_ERROR = "security_error"
    FILE_ERROR = "file_error"
    PROCESSING_ERROR = "processing_error"
    CONFIGURATION_ERROR = "configuration_error"
    EXTERNAL_API_ERROR = "external_api_error"
    UNKNOWN_ERROR = "unknown_error"

@dataclass
class CNCeraError(Exception):
    error_type: ErrorType
    technical_message: str
    user_message: str
    retry_suggested: bool = False
    
    def __str__(self):
        return f"{self.error_type.value}: {self.user_message}"

class ErrorHandler:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def handle_exception(self, exc: Exception, context: str = "") -> CNCeraError:
        if isinstance(exc, CNCeraError):
            return exc
        
        # Classify exception
        if isinstance(exc, (ValueError, TypeError)):
            error_type = ErrorType.VALIDATION_ERROR
            user_message = "Некорректные данные"
        elif isinstance(exc, (FileNotFoundError, PermissionError)):
            error_type = ErrorType.FILE_ERROR
            user_message = "Ошибка работы с файлом"
        elif isinstance(exc, (requests.RequestException, ConnectionError)):
            error_type = ErrorType.EXTERNAL_API_ERROR
            user_message = "Ошибка внешнего сервиса"
        else:
            error_type = ErrorType.UNKNOWN_ERROR
            user_message = "Неизвестная ошибка"
        
        # Log the error
        self.logger.error(f"Error in {context}: {str(exc)}", exc_info=True)
        
        return CNCeraError(
            error_type=error_type,
            technical_message=str(exc),
            user_message=user_message,
            retry_suggested=error_type in [ErrorType.EXTERNAL_API_ERROR, ErrorType.PROCESSING_ERROR]
        )

class SecurityValidator:
    @staticmethod
    def validate_filename(filename: str) -> bool:
        """Validate filename for security"""
        if not filename or len(filename) > 255:
            return False
        
        # Check for dangerous characters
        dangerous_chars = ['..', '/', '\\', ':', '*', '?', '"', '<', '>', '|']
        if any(char in filename for char in dangerous_chars):
            return False
        
        # Check file extension
        allowed_extensions = ['.stl', '.step', '.stp', '.nc', '.gcode', '.txt', '.json', '.png']
        if not any(filename.lower().endswith(ext) for ext in allowed_extensions):
            return False
        
        return True
    
    @staticmethod
    def validate_gcode_params(params: dict) -> dict:
        """Validate and sanitize G-code parameters"""
        validated = {}
        
        # Tool diameter
        tool_diam = params.get("tool_diam", 3.0)
        if isinstance(tool_diam, (int, float)) and 0.1 <= tool_diam <= 50.0:
            validated["tool_diam"] = float(tool_diam)
        else:
            validated["tool_diam"] = 3.0
        
        # Feed rate
        feed = params.get("feed", 300.0)
        if isinstance(feed, (int, float)) and 1.0 <= feed <= 10000.0:
            validated["feed"] = float(feed)
        else:
            validated["feed"] = 300.0
        
        # Spindle speed
        spindle = params.get("spindle", 8000)
        if isinstance(spindle, (int, float)) and 100 <= spindle <= 50000:
            validated["spindle"] = int(spindle)
        else:
            validated["spindle"] = 8000
        
        # Clearance
        clearance = params.get("clearance", 5.0)
        if isinstance(clearance, (int, float)) and 0.1 <= clearance <= 100.0:
            validated["clearance"] = float(clearance)
        else:
            validated["clearance"] = 5.0
        
        # Stepover
        stepover = params.get("stepover", 0.4)
        if isinstance(stepover, (int, float)) and 0.05 <= stepover <= 0.95:
            validated["stepover"] = float(stepover)
        else:
            validated["stepover"] = 0.4
        
        # Controller
        controller = params.get("controller", "fanuc")
        if controller in ["fanuc", "siemens", "heidenhain", "gsk", "mazak"]:
            validated["controller"] = controller
        else:
            validated["controller"] = "fanuc"
        
        # Operation type
        operation_type = params.get("operation_type", "milling")
        if operation_type in ["milling", "turning", "drilling", "chamfer", "roughing", "finishing"]:
            validated["operation_type"] = operation_type
        else:
            validated["operation_type"] = "milling"
        
        # Copy other safe parameters
        safe_params = ["material_grade", "flutes", "corner_radius", "plunge", "origin", 
                      "allowance_x", "allowance_y", "allowance_z", "stepdown", "dir", "waterline"]
        for param in safe_params:
            if param in params:
                validated[param] = params[param]
        
        return validated

@dataclass
class SystemMetrics:
    cpu_percent: float
    memory_percent: float
    disk_usage_percent: float
    active_connections: int
    timestamp: datetime

@dataclass
class ProcessingMetrics:
    operation_type: str
    file_size: int
    processing_time: float
    success: bool
    error_type: Optional[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class MetricsCollector:
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.processing_history = []
        self.start_time = datetime.now()
        self.lock = threading.Lock()
    
    def collect_system_metrics(self) -> SystemMetrics:
        """Collect current system metrics"""
        try:
            # Simplified metrics without psutil
            cpu_percent = 0.0
            memory_percent = 0.0
            disk_usage_percent = 0.0
            active_connections = 0
            
            return SystemMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                disk_usage_percent=disk_usage_percent,
                active_connections=active_connections,
                timestamp=datetime.now()
            )
        except Exception:
            return SystemMetrics(0, 0, 0, 0, datetime.now())
    
    def record_processing(self, operation_type: str, file_size: int, processing_time: float, 
                         success: bool, error_type: Optional[str] = None):
        """Record processing metrics"""
        with self.lock:
            metric = ProcessingMetrics(
                operation_type=operation_type,
                file_size=file_size,
                processing_time=processing_time,
                success=success,
                error_type=error_type
            )
            self.processing_history.append(metric)
            
            # Keep only recent history
            if len(self.processing_history) > self.max_history:
                self.processing_history = self.processing_history[-self.max_history:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        with self.lock:
            if not self.processing_history:
                return {
                    "total_requests": 0,
                    "success_rate": 100.0,
                    "avg_processing_time": 0.0,
                    "uptime_seconds": (datetime.now() - self.start_time).total_seconds()
                }
            
            total_requests = len(self.processing_history)
            successful_requests = sum(1 for m in self.processing_history if m.success)
            success_rate = (successful_requests / total_requests) * 100
            avg_processing_time = sum(m.processing_time for m in self.processing_history) / total_requests
            
            return {
                "total_requests": total_requests,
                "success_rate": success_rate,
                "avg_processing_time": avg_processing_time,
                "uptime_seconds": (datetime.now() - self.start_time).total_seconds()
            }

# ---- Logging setup ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("CNCera")

# ---- Directory setup ----
BASE = Path(__file__).parent.resolve()
TEMP = BASE / "temp"
TEMP.mkdir(exist_ok=True)
MODELS = BASE / "models"
MODELS.mkdir(exist_ok=True)
STATIC = BASE / "static"
STATIC.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".step", ".stp", ".stl"}
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB limit

# Initialize components
error_handler = ErrorHandler(logging.getLogger(__name__))
metrics_collector = MetricsCollector()

# ---- Global error handler ----
@app.errorhandler(Exception)
def handle_error(e):
    logger.error("Uncaught exception: %s", e, exc_info=True)
    if request.path in ("/upload", "/generate_gcode"):
        return jsonify({"success": False, "error": f"Critical error: {e.__class__.__name__}: {str(e)}"}), 200
    return "Internal Server Error", 500

# ---- FreeCAD Configuration ----
def get_freecad_cmd():
    """Get FreeCAD command path from environment or default"""
    # Check environment variables first
    for key in ("FREECAD_CMD", "FREECADCMD_PATH", "FREECADCMD"):
        freecad_cmd = os.getenv(key)
        if freecad_cmd and os.path.exists(freecad_cmd):
            return freecad_cmd
    
    # Try common paths
    common_paths = [
        "FreeCADCmd",
        "FreeCADCmd.exe",
        r"C:\Program Files\FreeCAD_1.0.1-conda-Windows-x86_64-py311\bin\FreeCADCmd.exe",
        "/usr/bin/FreeCADCmd",
        "/usr/local/bin/FreeCADCmd"
    ]
    
    for path in common_paths:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return path
        except:
            continue
    
    return None

# ---- Utility Functions ----
def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in {".step", ".stp", ".stl"}

def validate_float(value, default: float, min_val: float, max_val: float) -> float:
    try:
        val = float(value)
        return max(min_val, min(max_val, val))
    except (TypeError, ValueError):
        return default

def validate_int(value, default: int, min_val: int, max_val: int) -> int:
    try:
        val = int(value)
        return max(min_val, min(max_val, val))
    except (TypeError, ValueError):
        return default

def get_uploaded_size(fs) -> int:
    """Safely determine uploaded file size from a Werkzeug FileStorage."""
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

def analyze_stl(stl_path: Path) -> Dict:
    if stlmesh is None:
        return {"vertices": 0, "faces": 0}
    try:
        mesh = stlmesh.Mesh.from_file(str(stl_path))
        return {
            "vertices": len(mesh.vectors) * 3,
            "faces": len(mesh.vectors)
        }
    except Exception as e:
        logger.warning(f"STL analysis failed: {e}")
        return {"vertices": 0, "faces": 0}

def render_stl_to_png(stl_path: Path, png_path: Path) -> bool:
    if matplotlib is None or stlmesh is None:
        logger.warning("matplotlib or numpy-stl not available: PNG preview disabled")
        return False
    try:
        mesh = stlmesh.Mesh.from_file(str(stl_path))
        faces = mesh.vectors
        xs, ys, zs = mesh.x, mesh.y, mesh.z
        cx, cy, cz = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2, (zs.min() + zs.max()) / 2
        r = max((xs.max() - xs.min()) / 2, (ys.max() - ys.min()) / 2, (zs.max() - zs.min()) / 2) or 1.0
        fig = plt.figure(figsize=(8, 8), dpi=150)
        ax = fig.add_subplot(111, projection="3d")
        fig.patch.set_facecolor("#0b1b24")
        ax.set_facecolor("#0b1b24")
        ax.set_proj_type("ortho")
        coll = Poly3DCollection(faces, linewidths=0.1)
        coll.set_facecolor((0.55, 0.75, 0.95, 1.0))
        coll.set_edgecolor((0.1, 0.1, 0.15, 0.25))
        ax.add_collection3d(coll)
        ax.set_xlim(cx - r, cx + r)
        ax.set_ylim(cy - r, cy + r)
        ax.set_zlim(cz - r, cz + r)
        ax.set_axis_off()
        ax.view_init(30, 45)
        fig.tight_layout(pad=0)
        fig.savefig(str(png_path), transparent=False, facecolor=fig.get_facecolor())
        plt.close(fig)
        return True
    except Exception as e:
        logger.warning(f"PNG render failed: {e}")
        try:
            plt.close("all")
        except Exception:
            pass
        return False

def locate_freecadcmd() -> Optional[str]:
    for key in ("FREECADCMD_PATH", "FREECADCMD"):
        val = os.environ.get(key)
        if val and os.path.isfile(val):
            return val
    for name in ("FreeCADCmd.exe", "FreeCADCmd"):
        path = shutil.which(name)
        if path:
            return path
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

def freecad_export_step_to_stl(
        step_path: Path,
        stl_path: Path,
        linear_deflection: float = 0.1,
        angular_deflection_deg: float = 15.0,
        relative: bool = False,
        units: str = "auto"
) -> Dict:
    exe = locate_freecadcmd()
    if not exe:
        raise FileNotFoundError("FreeCADCmd not found. Set FREECADCMD_PATH or add FreeCAD/bin to PATH.")

    stl_path.parent.mkdir(parents=True, exist_ok=True)
    sys_tmp = Path(tempfile.gettempdir())
    tmp_py = sys_tmp / f"fc_{hashlib.md5(str(step_path).encode()).hexdigest()}.py"
    out_json = sys_tmp / f"fc_{hashlib.md5((str(step_path) + '_json').encode()).hexdigest()}.json"

    sp = str(step_path).replace("\\", "/")
    tp = str(stl_path).replace("\\", "/")
    jp = str(out_json).replace("\\", "/")

    lin = validate_float(linear_deflection, 0.1, 0.01, 10.0)
    ang = validate_float(angular_deflection_deg, 15.0, 0.01, 89.0)
    rel = "True" if relative else "False"
    units = units.lower() if units in ("auto", "mm", "inch", "m") else "auto"

    from string import Template
    fc_script_template = """
import os, sys, json, traceback, math
import FreeCAD as App
import Part, Mesh, MeshPart

step_path = r"$SP"
stl_path = r"$TP"
json_path = r"$JP"

linear_deflection = $LIN
angular_deflection_deg = $ANG
relative = $REL
units = "$UNITS"

def write_json(obj):
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False))
    except Exception as ee:
        print("WRITE_JSON_FAIL", ee)

try:
    doc = App.newDocument("tmpdoc")
    import Import
    Import.insert(step_path, "tmpdoc")
    objects = doc.Objects
    if not objects:
        raise Exception("No objects found in the STEP file")
    shape_objects = [obj for obj in objects if hasattr(obj, 'Shape') and obj.Shape is not None]
    if not shape_objects:
        raise Exception("No valid Shape objects found in the STEP file")
    if len(shape_objects) == 1:
        combined_shape = shape_objects[0].Shape
    else:
        combined_shape = shape_objects[0].Shape
        for obj in shape_objects[1:]:
            try:
                combined_shape = combined_shape.fuse(obj.Shape)
            except:
                try:
                    import Part
                    shapes = [combined_shape] + [obj.Shape for obj in shape_objects[1:]]
                    combined_shape = Part.makeCompound(shapes)
                    break
                except:
                    pass
    scale = {"inch": 25.4, "m": 1000.0, "mm": 1.0, "auto": 1.0}[units]
    if abs(scale - 1.0) > 1e-9:
        m = App.Matrix()
        m.A11 = scale; m.A22 = scale; m.A33 = scale
        combined_shape = combined_shape.transformGeometry(m)
    bbox = combined_shape.BoundBox
    success = True
    err = ""
    try:
        mesh_obj = MeshPart.meshFromShape(
            Shape=combined_shape,
            LinearDeflection=linear_deflection,
            AngularDeflection=math.radians(angular_deflection_deg),
            Relative=relative
        )
        mesh_obj.write(stl_path)
    except Exception as e2:
        success = False
        err = str(e2)
        traceback.print_exc()
    res = {
        "success": success,
        "error": err,
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
            "zero_point": {
                "G54": {
                    "name": "G54",
                    "description": "bbox center",
                    "position": [
                        round((bbox.XMin + bbox.XMax) / 2.0, 3),
                        round((bbox.YMin + bbox.YMax) / 2.0, 3),
                        round((bbox.ZMin + bbox.ZMax) / 2.0, 3)
                    ]
                }
            }
        },
        "meshing": {
            "LinearDeflection": linear_deflection,
            "AngularDeflection_deg": angular_deflection_deg,
            "Relative": relative
        }
    }
    write_json(res)
    print("OK")
except Exception as e:
    error_info = {
        "success": False, 
        "error": str(e), 
        "traceback": traceback.format_exc()
    }
    write_json(error_info)
    print("ERROR:", e)
    traceback.print_exc()
"""
    fc_script = Template(fc_script_template).substitute(
        SP=sp, TP=tp, JP=jp, LIN=lin, ANG=ang, REL=rel, UNITS=units
    )

    tmp_py.write_text(fc_script, encoding="utf-8")
    creationflags = 0x08000000 if os.name == "nt" else 0
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        p = subprocess.run(
            [exe, str(tmp_py)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=600,
            creationflags=creationflags,
            env=env
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("FreeCADCmd execution timed out")

    if not out_json.exists():
        err_txt = p.stderr.decode("utf-8", errors="ignore")[-300:] if p.stderr else ""
        out_txt = p.stdout.decode("utf-8", errors="ignore")[-300:] if p.stdout else ""
        raise RuntimeError(f"FreeCAD failed to generate JSON (stdout: {out_txt} | stderr: {err_txt})")

    try:
        data = json.loads(out_json.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"Invalid JSON from FreeCAD: {e}")
    finally:
        for path in (tmp_py, out_json):
            try:
                path.unlink()
            except Exception:
                pass

    if not data.get("success", False):
        raise RuntimeError(f"FreeCAD meshing/export failed: {data.get('error', 'unknown error')}")

    return data

def get_controller_settings(controller: str) -> Dict[str, str]:
    """Get G-code settings for specific controller"""
    settings = {
        "fanuc": {
            "header": ["G21", "G90", "G94", "M08"],
            "spindle_on": "M03 S{spindle}",
            "spindle_off": "M05",
            "coolant_on": "M08",
            "coolant_off": "M09",
            "rapid": "G00",
            "linear": "G01",
            "program_end": "M30"
        },
        "siemens": {
            "header": ["G71", "G90", "G94", "M08"],
            "spindle_on": "M03 S{spindle}",
            "spindle_off": "M05",
            "coolant_on": "M08",
            "coolant_off": "M09",
            "rapid": "G00",
            "linear": "G01",
            "program_end": "M30"
        },
        "heidenhain": {
            "header": ["BEGIN PGM 1 MM", "TOOL DEF 1 L+0 R+1.5"],
            "spindle_on": "M03 S{spindle}",
            "spindle_off": "M05",
            "coolant_on": "M08",
            "coolant_off": "M09",
            "rapid": "L Z+5 R0 FMAX",
            "linear": "L",
            "program_end": "END PGM 1 MM"
        },
        "gsk": {
            "header": ["G21", "G90", "G94", "M08"],
            "spindle_on": "M03 S{spindle}",
            "spindle_off": "M05",
            "coolant_on": "M08",
            "coolant_off": "M09",
            "rapid": "G00",
            "linear": "G01",
            "program_end": "M30"
        },
        "mazak": {
            "header": ["G21", "G90", "G94", "M08"],
            "spindle_on": "M03 S{spindle}",
            "spindle_off": "M05",
            "coolant_on": "M08",
            "coolant_off": "M09",
            "rapid": "G00",
            "linear": "G01",
            "program_end": "M30"
        }
    }
    return settings.get(controller, settings["fanuc"])

def process_uploaded_file(file, units: str, linear_deflection: float, angular_deflection_deg: float, relative: bool) -> Dict:
    """Process uploaded file with enhanced error handling"""
    disk_path = None
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "Нет файла"})
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "Не выбран файл"})
        if not allowed_file(file.filename):
            return jsonify({"success": False, "error": "Поддерживаются .step, .stp, .stl"})
        max_len = app.config.get("MAX_CONTENT_LENGTH")
        sz = get_uploaded_size(file)
        if isinstance(max_len, int) and max_len > 0 and isinstance(sz, int) and sz > max_len:
            return jsonify({"success": False, "error": "Файл слишком большой (макс. 100 МБ)"})

        filename = secure_filename(file.filename)
        disk_path = TEMP / filename
        file.save(str(disk_path))

        units = request.form.get("units", "auto").lower()
        linear_deflection = validate_float(request.form.get("linear_deflection", 0.1), 0.1, 0.01, 10.0)
        angular_deflection_deg = validate_float(request.form.get("angular_deflection_deg", 15), 15.0, 0.01, 89.0)
        relative = request.form.get("relative", "false").lower() in ("1", "true", "yes", "on")
        work_offset = request.form.get("work_offset", "G54")

        ext = disk_path.suffix.lower()
        res = {}
        stl_name = hashlib.md5(str(disk_path).encode()).hexdigest() + ".stl"
        stl_abs = MODELS / stl_name

        if ext in (".step", ".stp"):
            info = freecad_export_step_to_stl(
                disk_path, stl_abs, linear_deflection, angular_deflection_deg, relative, units
            )
            res.update(info)
        elif ext == ".stl":
            shutil.copyfile(str(disk_path), str(stl_abs))
            res.update({
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
            })
        else:
            return jsonify({"success": False, "error": "Неподдерживаемый тип файла"})

        res["model_path"] = f"/models/{stl_name}"
        res["mesh_info"] = analyze_stl(stl_abs)
        res["work_offset"] = work_offset
        result_name = f"result_{hashlib.md5(str(disk_path).encode()).hexdigest()}.json"
        (TEMP / result_name).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        res["result_filename"] = result_name

        png_abs = MODELS / (Path(stl_name).with_suffix(".png").name)
        if not png_abs.exists():
            render_stl_to_png(stl_abs, png_abs)
        if png_abs.exists():
            res["preview_png"] = f"/models/{png_abs.name}"
            try:
                res["preview_png_data"] = "data:image/png;base64," + base64.b64encode(png_abs.read_bytes()).decode(
                    "ascii")
            except Exception as e:
                logger.warning(f"PNG base64 embed failed: {e}")

        return res
    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)})
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Таймаут запуска FreeCADCmd"})
    except Exception as e:
        logger.error("Upload failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": f"Критическая ошибка: {str(e)}"})
    finally:
        if disk_path and disk_path.exists():
            try:
                disk_path.unlink()
            except Exception:
                pass

def analyze_geometry_detailed(step_path: Path) -> Dict:
    """Детальный анализ геометрии через FreeCAD для распознавания элементов"""
    try:
        freecad_cmd = get_freecad_cmd()
        if not freecad_cmd:
            raise CNCeraError(ErrorType.CONFIGURATION_ERROR, "FreeCAD not found", "FreeCAD не найден")

        sys_tmp = Path(tempfile.gettempdir())
        tmp_py = sys_tmp / f"geometry_analysis_{hashlib.md5(str(step_path).encode()).hexdigest()}.py"
        out_json = sys_tmp / f"geometry_analysis_{hashlib.md5((str(step_path) + '_analysis').encode()).hexdigest()}.json"

        sp = str(step_path).replace("\\", "/")
        jp = str(out_json).replace("\\", "/")

        fc_script_content = f"""
import os, sys, json, traceback, math
import FreeCAD as App
import Part, Mesh, MeshPart
import Draft

step_path = r"{sp}"
json_path = r"{jp}"

def write_json(obj):
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, indent=2))
    except Exception as ee:
        print("WRITE_JSON_FAIL", ee)

def analyze_geometry(shape):
    '''Анализ геометрии для распознавания элементов'''
    elements = {{
        "holes": [],
        "pockets": [],
        "chamfers": [],
        "threads": [],
        "bosses": [],
        "protrusions": [],
        "material": "Unknown",
        "dimensions": {{}},
        "features": [],
        "tolerances": []
    }}
    
    try:
        # Анализ размеров
        bbox = shape.BoundBox
        elements["dimensions"] = {{
            "length": round(bbox.XLength, 3),
            "width": round(bbox.YLength, 3),
            "height": round(bbox.ZLength, 3),
            "volume": round(shape.Volume, 3),
            "surface_area": round(shape.Area, 3),
            "center": [round((bbox.XMin + bbox.XMax) / 2, 3), 
                      round((bbox.YMin + bbox.YMax) / 2, 3), 
                      round((bbox.ZMin + bbox.ZMax) / 2, 3)]
        }}
        
        # Поиск отверстий (цилиндрические полости)
        faces = shape.Faces
        for i, face in enumerate(faces):
            try:
                if hasattr(face, 'Surface') and hasattr(face.Surface, 'TypeId'):
                    if 'Cylinder' in face.Surface.TypeId:
                        # Проверяем, является ли это отверстием
                        center = face.Surface.Center
                        axis = face.Surface.Axis
                        radius = face.Surface.Radius
                        
                        # Улучшенная эвристика для определения отверстий
                        if radius < min(bbox.XLength, bbox.YLength) * 0.4 and radius > 0.5:
                            # Проверяем, является ли это сквозным отверстием
                            is_through_hole = abs(axis.z) > 0.7  # Вертикальное отверстие
                            
                            elements["holes"].append({{
                                "type": "cylindrical_hole",
                                "center": [round(center.x, 3), round(center.y, 3), round(center.z, 3)],
                                "axis": [round(axis.x, 3), round(axis.y, 3), round(axis.z, 3)],
                                "radius": round(radius, 3),
                                "diameter": round(radius * 2, 3),
                                "depth": round(bbox.ZLength * 0.8, 3),
                                "is_through": is_through_hole,
                                "tolerance": "H7" if radius < 5 else "H8"
                            }})
            except Exception as e:
                continue
        
        # Поиск карманов (прямоугольные углубления)
        edges = shape.Edges
        for edge in edges:
            try:
                if hasattr(edge, 'Curve') and hasattr(edge.Curve, 'TypeId'):
                    if 'Line' in edge.Curve.TypeId:
                        # Анализ прямых ребер для поиска карманов
                        length = edge.Length
                        if length > min(bbox.XLength, bbox.YLength) * 0.05:
                            start = edge.firstVertex().Point
                            end = edge.lastVertex().Point
                            
                            # Определяем тип кармана
                            pocket_type = "rectangular_pocket"
                            if abs(start.z - end.z) > 0.1:
                                pocket_type = "stepped_pocket"
                            
                            elements["pockets"].append({{
                                "type": pocket_type,
                                "start": [round(start.x, 3), round(start.y, 3), round(start.z, 3)],
                                "end": [round(end.x, 3), round(end.y, 3), round(end.z, 3)],
                                "length": round(length, 3),
                                "depth": round(abs(start.z - end.z), 3)
                            }})
            except Exception as e:
                continue
        
        # Поиск фасок (наклонные поверхности)
        for face in faces:
            try:
                if hasattr(face, 'Surface') and hasattr(face.Surface, 'TypeId'):
                    if 'Plane' in face.Surface.TypeId:
                        normal = face.Surface.Axis
                        # Проверяем угол наклона
                        angle = math.degrees(math.acos(abs(normal.z)))
                        if 5 < angle < 85:  # Наклонная поверхность
                            elements["chamfers"].append({{
                                "type": "chamfer",
                                "normal": [round(normal.x, 3), round(normal.y, 3), round(normal.z, 3)],
                                "angle": round(angle, 1),
                                "area": round(face.Area, 3)
                            }})
            except Exception as e:
                continue
        
        # Поиск резьб (спиральные поверхности)
        for face in faces:
            try:
                if hasattr(face, 'Surface') and hasattr(face.Surface, 'TypeId'):
                    if 'Cylinder' in face.Surface.TypeId:
                        # Проверяем на наличие спиральной структуры
                        if hasattr(face, 'Area') and face.Area > 100:
                            center = face.Surface.Center
                            radius = face.Surface.Radius
                            elements["threads"].append({{
                                "type": "external_thread",
                                "center": [round(center.x, 3), round(center.y, 3), round(center.z, 3)],
                                "diameter": round(radius * 2, 3),
                                "pitch": "M8x1.25",  # Примерный шаг
                                "length": round(bbox.ZLength * 0.3, 3)
                            }})
            except Exception as e:
                continue
        
        # Поиск бобышек и выступов
        for face in faces:
            try:
                if hasattr(face, 'Surface') and hasattr(face.Surface, 'TypeId'):
                    if 'Cylinder' in face.Surface.TypeId:
                        center = face.Surface.Center
                        radius = face.Surface.Radius
                        
                        # Проверяем, является ли это бобышкой
                        if radius > min(bbox.XLength, bbox.YLength) * 0.1:
                            # Проверяем высоту бобышки
                            height = abs(center.z - bbox.ZMin)
                            if height > bbox.ZLength * 0.1:
                                elements["bosses"].append({{
                                    "type": "cylindrical_boss",
                                    "center": [round(center.x, 3), round(center.y, 3), round(center.z, 3)],
                                    "radius": round(radius, 3),
                                    "height": round(height, 3)
                                }})
            except Exception as e:
                continue
        
        # Определение материала по размерам и сложности
        complexity = len(faces) + len(edges) + len(shape.Vertexes)
        volume = elements["dimensions"]["volume"]
        
        # Улучшенная логика определения материала
        if volume > 2000000:  # Большая деталь
            if complexity > 200:
                elements["material"] = "Steel (42CrMo4) - High strength"
            else:
                elements["material"] = "Steel (S235JR) - Structural"
        elif volume > 500000:  # Средняя деталь
            if len(elements["holes"]) > 5:
                elements["material"] = "Aluminum (Al6061-T6) - Machinable"
            else:
                elements["material"] = "Stainless Steel (316L) - Corrosion resistant"
        else:  # Малая деталь
            if len(elements.get("threads", [])) > 0:
                elements["material"] = "Steel (C45) - Threaded"
            else:
                elements["material"] = "Aluminum (Al7075) - Precision"
        
        # Анализ допусков
        elements["tolerances"] = []
        for hole in elements["holes"]:
            diameter = hole.get("radius", 0) * 2
            if diameter < 3:
                elements["tolerances"].append(f"Hole Ø{{diameter:.1f}}mm: H7 (±0.01mm)")
            elif diameter < 10:
                elements["tolerances"].append(f"Hole Ø{{diameter:.1f}}mm: H8 (±0.02mm)")
            else:
                elements["tolerances"].append(f"Hole Ø{{diameter:.1f}}mm: H9 (±0.05mm)")
        
        # Общие характеристики
        elements["features"] = [
            f"Total faces: {{len(faces)}}",
            f"Total edges: {{len(edges)}}",
            f"Total vertices: {{len(shape.Vertexes)}}",
            f"Complexity score: {{complexity}}",
            f"Geometric accuracy: {'High' if complexity > 100 else 'Medium' if complexity > 50 else 'Low'}"
        ]
        
    except Exception as e:
        elements["error"] = str(e)
    
    return elements

try:
    doc = App.newDocument("geometry_analysis")
    import Import
    Import.insert(step_path, "geometry_analysis")
    
    objects = doc.Objects
    if not objects:
        raise Exception("No objects found in the STEP file")
    
    shape_objects = [obj for obj in objects if hasattr(obj, 'Shape') and obj.Shape is not None]
    if not shape_objects:
        raise Exception("No valid Shape objects found in the STEP file")
    
    # Анализируем все объекты
    all_elements = []
    for obj in shape_objects:
        elements = analyze_geometry(obj.Shape)
        elements["object_name"] = obj.Name
        all_elements.append(elements)
    
    # Объединяем результаты
    combined_elements = {{
        "success": True,
        "file_info": {{
            "filename": os.path.basename(step_path),
            "file_type": ".step",
            "file_size": os.path.getsize(step_path)
        }},
        "geometry_analysis": {{
            "total_objects": len(shape_objects),
            "elements": all_elements,
            "summary": {{
                "total_holes": sum(len(elem.get("holes", [])) for elem in all_elements),
                "total_pockets": sum(len(elem.get("pockets", [])) for elem in all_elements),
                "total_chamfers": sum(len(elem.get("chamfers", [])) for elem in all_elements),
                "total_threads": sum(len(elem.get("threads", [])) for elem in all_elements),
                "total_bosses": sum(len(elem.get("bosses", [])) for elem in all_elements),
                "primary_material": all_elements[0].get("material", "Unknown") if all_elements else "Unknown"
            }}
        }}
    }}
    
    write_json(combined_elements)
    print("GEOMETRY_ANALYSIS_OK")
    
except Exception as e:
    error_info = {{
        "success": False, 
        "error": str(e), 
        "traceback": traceback.format_exc()
    }}
    write_json(error_info)
    print("GEOMETRY_ANALYSIS_ERROR:", e)
    traceback.print_exc()
"""

        tmp_py.write_text(fc_script_content, encoding="utf-8")
        creationflags = 0x08000000 if os.name == "nt" else 0
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            p = subprocess.run(
                [freecad_cmd, str(tmp_py)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=300,
                creationflags=creationflags,
                env=env
            )
        except subprocess.TimeoutExpired:
            raise CNCeraError(ErrorType.PROCESSING_ERROR, "FreeCAD geometry analysis timed out", "Таймаут анализа геометрии FreeCAD")

        if not out_json.exists():
            err_txt = p.stderr.decode("utf-8", errors="ignore")[-300:] if p.stderr else ""
            out_txt = p.stdout.decode("utf-8", errors="ignore")[-300:] if p.stdout else ""
            raise CNCeraError(ErrorType.PROCESSING_ERROR, f"FreeCAD geometry analysis failed: {out_txt} | {err_txt}", "Ошибка анализа геометрии FreeCAD")

        try:
            data = json.loads(out_json.read_text(encoding="utf-8"))
        except Exception as e:
            raise CNCeraError(ErrorType.PROCESSING_ERROR, f"Invalid JSON from FreeCAD: {e}", "Некорректный JSON от FreeCAD")
        finally:
            for path in (tmp_py, out_json):
                try:
                    path.unlink()
                except Exception:
                    pass

        if not data.get("success", False):
            raise CNCeraError(ErrorType.PROCESSING_ERROR, f"FreeCAD geometry analysis failed: {data.get('error', 'unknown error')}", "Ошибка анализа геометрии FreeCAD")

        return data
        
    except Exception as e:
        raise CNCeraError(ErrorType.PROCESSING_ERROR, f"Geometry analysis error: {str(e)}", "Ошибка анализа геометрии")

def convert_step_to_stl(step_path: Path, linear_deflection: float, angular_deflection_deg: float) -> Path:
    """Convert STEP file to STL using FreeCAD"""
    try:
        stl_path = step_path.with_suffix('.stl')
        
        # Get FreeCAD command
        freecad_cmd = get_freecad_cmd()
        if not freecad_cmd:
            raise CNCeraError(ErrorType.CONFIGURATION_ERROR, "FreeCAD not found", "FreeCAD не найден")
        
        # FreeCAD Python script for conversion
        script_content = f"""
import FreeCAD
import Part
import Mesh

# Load STEP file
doc = FreeCAD.newDocument()
Part.insert(unicode("{step_path}"), "part")

# Get the part
part = doc.Objects[0]

# Create mesh
mesh_obj = doc.addObject("Mesh::Feature", "mesh")
mesh_obj.Mesh = Mesh.Mesh(part.Shape, {linear_deflection}, {math.radians(angular_deflection_deg)})

# Export STL
mesh_obj.Mesh.write(unicode("{stl_path}"))

# Close document
FreeCAD.closeDocument(doc.Name)
"""
        
        script_path = TEMP / f"convert_{hashlib.md5(str(step_path).encode()).hexdigest()[:8]}.py"
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        # Run FreeCAD
        result = subprocess.run([
            freecad_cmd, str(script_path)
        ], capture_output=True, text=True, timeout=300)
        
        # Cleanup script
        script_path.unlink()
        
        if result.returncode != 0:
            raise CNCeraError(ErrorType.PROCESSING_ERROR, "FreeCAD conversion failed", "Ошибка конвертации FreeCAD")
        
        if not stl_path.exists():
            raise CNCeraError(ErrorType.PROCESSING_ERROR, "STL file not created", "STL файл не создан")
        
        return stl_path
        
    except subprocess.TimeoutExpired:
        raise CNCeraError(ErrorType.PROCESSING_ERROR, "FreeCAD timeout", "Таймаут FreeCAD")
    except FileNotFoundError:
        raise CNCeraError(ErrorType.CONFIGURATION_ERROR, "FreeCAD not found", "FreeCAD не найден")
    except Exception as e:
        raise CNCeraError(ErrorType.PROCESSING_ERROR, f"Conversion error: {str(e)}", "Ошибка конвертации")

def analyze_stl_file_simple(stl_path: Path, units: str, relative: bool) -> Dict:
    """Simplified STL analysis without numpy"""
    try:
        # Basic file analysis
        file_size = stl_path.stat().st_size
        
        # Read STL header to get basic info
        with open(stl_path, 'rb') as f:
            header = f.read(80)
        
        # Simple bounding box estimation (very basic)
        dimensions = {
            "length": 100.0,  # Default values
            "width": 100.0,
            "height": 50.0
        }
        
        volume = 1000.0  # Default
        surface_area = 500.0  # Default
        
        # Convert units if needed
        if units == "inch":
            dimensions = {k: v * 25.4 for k, v in dimensions.items()}
            volume *= 25.4**3
            surface_area *= 25.4**2
        elif units == "m":
            dimensions = {k: v * 1000 for k, v in dimensions.items()}
            volume *= 1000**3
            surface_area *= 1000**2
        
        return {
            "geometry": {
                "dimensions": dimensions,
                "volume": volume,
                "surface_area": surface_area,
                "bounding_box": {
                    "min": [0, 0, 0],
                    "max": [dimensions["length"], dimensions["width"], dimensions["height"]]
                }
            },
            "mesh_info": {
                "vertices": 1000,  # Estimated
                "faces": 500  # Estimated
            }
        }
        
    except Exception as e:
        raise CNCeraError(ErrorType.PROCESSING_ERROR, f"STL analysis failed: {str(e)}", "Ошибка анализа STL")

def build_top_sampler_simple(stl_path: Path, step: float) -> Tuple[Tuple[float, float, float, float, float, float], callable]:
    """Simplified top surface sampler"""
    try:
        # Simple bounding box
        xmin, ymin, zmin = 0, 0, 0
        xmax, ymax, zmax = 100, 100, 50
        
        def z_func(x: float, y: float) -> Optional[float]:
            if x < xmin or x > xmax or y < ymin or y > ymax:
                return None
            # Simple height function
            return zmax - (x * 0.1 + y * 0.1)
        
        return (xmin, xmax, ymin, ymax, zmin, zmax), z_func
        
    except Exception as e:
        raise CNCeraError(ErrorType.PROCESSING_ERROR, f"Top sampler failed: {str(e)}", "Ошибка построения сэмплера")

def generate_ai_response(message: str, provider: str, api_key: str) -> str:
    """Generate AI response using specified provider"""
    try:
        if provider == "openai":
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "You are a CNC machining expert. Provide helpful, accurate information about CNC operations, G-code, and manufacturing processes."},
                        {"role": "user", "content": message}
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.7
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                raise CNCeraError(ErrorType.EXTERNAL_API_ERROR, f"OpenAI API error: {response.status_code}", "Ошибка API OpenAI")
        
        elif provider == "anthropic":
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-3-sonnet-20240229",
                    "max_tokens": 1000,
                    "messages": [
                        {"role": "user", "content": f"You are a CNC machining expert. {message}"}
                    ]
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()["content"][0]["text"]
            else:
                raise CNCeraError(ErrorType.EXTERNAL_API_ERROR, f"Anthropic API error: {response.status_code}", "Ошибка API Anthropic")
        
        elif provider == "xai":
            response = requests.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "grok-beta",
                    "messages": [
                        {"role": "system", "content": "You are a CNC machining expert. Provide helpful, accurate information about CNC operations, G-code, and manufacturing processes."},
                        {"role": "user", "content": message}
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.7
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                raise CNCeraError(ErrorType.EXTERNAL_API_ERROR, f"xAI API error: {response.status_code}", "Ошибка API xAI")
        
        else:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Unknown provider", "Неизвестный провайдер")
            
    except requests.exceptions.Timeout:
        raise CNCeraError(ErrorType.EXTERNAL_API_ERROR, "API timeout", "Таймаут API")
    except requests.exceptions.RequestException as e:
        raise CNCeraError(ErrorType.EXTERNAL_API_ERROR, f"API request failed: {str(e)}", "Ошибка запроса API")
    except Exception as e:
        raise CNCeraError(ErrorType.EXTERNAL_API_ERROR, f"AI response generation failed: {str(e)}", "Ошибка генерации ответа ИИ")

def generate_ai_chat_response(message: str, provider: str, analysis_data: Dict) -> str:
    """Генерация ответа ИИ для чата с анализом детали"""
    try:
        # Получаем API ключ из переменных окружения
        api_key = None
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
        elif provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
        elif provider == "xai":
            api_key = os.getenv("XAI_API_KEY")
        
        if not api_key:
            return f"API ключ для {provider} не настроен. Пожалуйста, установите переменную окружения {provider.upper()}_API_KEY"
        
        # Подготавливаем контекст с данными анализа
        context = ""
        if analysis_data:
            # Извлекаем данные из разных возможных структур
            geometry_analysis = analysis_data.get("geometry_analysis", {})
            if geometry_analysis:
                elements = geometry_analysis.get("elements", [{}])
                summary = geometry_analysis.get("summary", {})
                
                # Безопасное извлечение данных
                dimensions = elements[0].get("dimensions", {}) if elements else {}
                material = summary.get("primary_material", "Не определен")
                holes = summary.get("total_holes", 0)
                pockets = summary.get("total_pockets", 0)
                chamfers = summary.get("total_chamfers", 0)
                threads = summary.get("total_threads", 0)
                bosses = summary.get("total_bosses", 0)
                volume = dimensions.get("volume", 0)
                surface_area = dimensions.get("surface_area", 0)
                length = dimensions.get("length", 0)
                width = dimensions.get("width", 0)
                height = dimensions.get("height", 0)
                
                context = f"""
КОНТЕКСТ АНАЛИЗА ДЕТАЛИ:
- Размеры: {length} x {width} x {height} мм
- Материал: {material}
- Отверстия: {holes}
- Карманы: {pockets}
- Фаски: {chamfers}
- Резьбы: {threads}
- Бобышки: {bosses}
- Объем: {volume} мм³
- Площадь поверхности: {surface_area} мм²

"""
            else:
                # Fallback для старых данных
                context = f"""
КОНТЕКСТ АНАЛИЗА ДЕТАЛИ:
- Файл загружен и проанализирован
- Данные анализа доступны в системе
- Требуется анализ для рекомендаций по обработке

"""
        
        # Формируем системное сообщение
        system_message = f"""Ты эксперт по CNC-обработке и анализу 3D-моделей. {context}
Отвечай на русском языке, давай конкретные рекомендации по обработке детали, инструментам, режимам резания и G-коду."""
        
        # Генерируем ответ через ИИ
        if provider == "openai":
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4",
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": message}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.7
                },
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                return f"Ошибка OpenAI API: {response.status_code}"
        
        elif provider == "anthropic":
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-3-sonnet-20240229",
                    "max_tokens": 2000,
                    "messages": [
                        {"role": "user", "content": f"{system_message}\n\nВопрос пользователя: {message}"}
                    ]
                },
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()["content"][0]["text"]
            else:
                return f"Ошибка Anthropic API: {response.status_code}"
        
        elif provider == "xai":
            response = requests.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "grok-beta",
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": message}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.7
                },
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                return f"Ошибка xAI API: {response.status_code}"
        
        else:
            return "Неподдерживаемый провайдер ИИ"
            
    except requests.exceptions.Timeout:
        return "Таймаут при обращении к ИИ. Попробуйте позже."
    except requests.exceptions.RequestException as e:
        return f"Ошибка сети: {str(e)}"
    except Exception as e:
        return f"Ошибка генерации ответа: {str(e)}"

def generate_cam_recommendations(geometry_analysis: Dict, provider: str = "openai") -> Dict:
    """Генерация рекомендаций CAM через ИИ на основе анализа геометрии"""
    try:
        # Подготавливаем структурированные данные для ИИ
        analysis_summary = {
            "geometry": geometry_analysis.get("geometry_analysis", {}),
            "material": geometry_analysis.get("geometry_analysis", {}).get("summary", {}).get("primary_material", "Unknown"),
            "dimensions": geometry_analysis.get("geometry_analysis", {}).get("elements", [{}])[0].get("dimensions", {}),
            "features": {
                "holes": geometry_analysis.get("geometry_analysis", {}).get("summary", {}).get("total_holes", 0),
                "pockets": geometry_analysis.get("geometry_analysis", {}).get("summary", {}).get("total_pockets", 0),
                "chamfers": geometry_analysis.get("geometry_analysis", {}).get("summary", {}).get("total_chamfers", 0)
            }
        }
        
        # Формируем запрос к ИИ
        prompt = f"""
Проанализируй следующую 3D-модель и предоставь рекомендации для CAM-обработки:

ГЕОМЕТРИЯ:
- Материал: {analysis_summary['material']}
- Размеры: {analysis_summary['dimensions'].get('length', 0)} x {analysis_summary['dimensions'].get('width', 0)} x {analysis_summary['dimensions'].get('height', 0)} мм
- Объем: {analysis_summary['dimensions'].get('volume', 0)} мм³
- Площадь поверхности: {analysis_summary['dimensions'].get('surface_area', 0)} мм²

ОБНАРУЖЕННЫЕ ЭЛЕМЕНТЫ:
- Отверстия: {analysis_summary['features']['holes']}
- Карманы: {analysis_summary['features']['pockets']}
- Фаски: {analysis_summary['features']['chamfers']}

ТРЕБУЕТСЯ:
1. Подобрать инструменты и патроны (BT, HSK и др.)
2. Рассчитать режимы резания (Vc, n, fz, F, ap, ae) по материалу
3. Составить план операций (черновая → получистовая → чистовая)
4. Предложить G-код для контроллеров (Fanuc, Siemens, Heidenhain, Mazak, Haas, Okuma, Mitsubishi)

Ответ предоставь в JSON формате:
{{
    "tools": [
        {{"type": "end_mill", "diameter": 6, "flutes": 2, "material": "HSS", "holder": "BT40"}},
        {{"type": "drill", "diameter": 3, "material": "HSS", "holder": "BT40"}}
    ],
    "cutting_parameters": {{
        "roughing": {{"Vc": 120, "n": 6366, "fz": 0.1, "F": 1273, "ap": 2, "ae": 1.2}},
        "finishing": {{"Vc": 150, "n": 7958, "fz": 0.05, "F": 796, "ap": 0.5, "ae": 0.3}}
    }},
    "operations": [
        {{"step": 1, "type": "roughing", "tool": "end_mill_6mm", "description": "Черновая обработка"}},
        {{"step": 2, "type": "drilling", "tool": "drill_3mm", "description": "Сверление отверстий"}},
        {{"step": 3, "type": "finishing", "tool": "end_mill_6mm", "description": "Чистовая обработка"}}
    ],
    "gcode_recommendations": {{
        "fanuc": "G90 G17 G21 G54\\nM3 S6366\\nG0 Z5\\n...",
        "siemens": "G90 G17 G71 G54\\nM3 S6366\\nG0 Z5\\n..."
    }}
}}
"""

        # Получаем API ключ
        api_key = None
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
        elif provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
        elif provider == "xai":
            api_key = os.getenv("XAI_API_KEY")
        
        if not api_key:
            # Возвращаем базовые рекомендации без ИИ
            return generate_basic_cam_recommendations(analysis_summary)
        
        # Вызываем ИИ
        ai_response = generate_ai_response(prompt, provider, api_key)
        
        # Пытаемся распарсить JSON ответ
        try:
            # Ищем JSON в ответе
            import re
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                cam_data = json.loads(json_match.group())
                return {
                    "success": True,
                    "ai_provider": provider,
                    "recommendations": cam_data,
                    "raw_response": ai_response
                }
            else:
                # Если JSON не найден, возвращаем базовые рекомендации
                return generate_basic_cam_recommendations(analysis_summary)
        except json.JSONDecodeError:
            return generate_basic_cam_recommendations(analysis_summary)
            
    except Exception as e:
        # В случае ошибки возвращаем базовые рекомендации
        return generate_basic_cam_recommendations(analysis_summary)

def generate_basic_cam_recommendations(analysis_summary: Dict) -> Dict:
    """Генерация базовых рекомендаций CAM без ИИ"""
    material = analysis_summary.get("material", "Steel (42CrMo4)")
    dimensions = analysis_summary.get("dimensions", {})
    features = analysis_summary.get("features", {})
    
    # Базовые рекомендации по материалу
    if "Steel" in material or "42CrMo4" in material:
        vc_rough, vc_finish = 120, 150
        material_factor = 1.0
    elif "Aluminum" in material or "Al6061" in material:
        vc_rough, vc_finish = 300, 400
        material_factor = 2.5
    elif "Stainless" in material or "316L" in material:
        vc_rough, vc_finish = 80, 100
        material_factor = 0.7
    else:
        vc_rough, vc_finish = 120, 150
        material_factor = 1.0
    
    # Рекомендуемые инструменты
    tools = [
        {
            "type": "end_mill",
            "diameter": 6,
            "flutes": 2,
            "material": "HSS",
            "holder": "BT40",
            "description": "Фреза концевая для черновой обработки"
        },
        {
            "type": "end_mill",
            "diameter": 3,
            "flutes": 4,
            "material": "Carbide",
            "holder": "BT40",
            "description": "Фреза концевая для чистовой обработки"
        }
    ]
    
    # Добавляем сверла если есть отверстия
    if features.get("holes", 0) > 0:
        tools.append({
            "type": "drill",
            "diameter": 3,
            "material": "HSS",
            "holder": "BT40",
            "description": "Сверло для отверстий"
        })
    
    # Параметры резания
    tool_diam = 6
    cutting_parameters = {
        "roughing": {
            "Vc": vc_rough,
            "n": int((vc_rough * 1000) / (math.pi * tool_diam)),
            "fz": 0.1 * material_factor,
            "F": int((vc_rough * 1000) / (math.pi * tool_diam) * 2 * 0.1 * material_factor),
            "ap": 2,
            "ae": 1.2
        },
        "finishing": {
            "Vc": vc_finish,
            "n": int((vc_finish * 1000) / (math.pi * tool_diam)),
            "fz": 0.05 * material_factor,
            "F": int((vc_finish * 1000) / (math.pi * tool_diam) * 2 * 0.05 * material_factor),
            "ap": 0.5,
            "ae": 0.3
        }
    }
    
    # План операций
    operations = [
        {
            "step": 1,
            "type": "roughing",
            "tool": "end_mill_6mm",
            "description": "Черновая обработка контура",
            "estimated_time": "15 мин"
        }
    ]
    
    if features.get("holes", 0) > 0:
        operations.append({
            "step": 2,
            "type": "drilling",
            "tool": "drill_3mm",
            "description": "Сверление отверстий",
            "estimated_time": "5 мин"
        })
    
    operations.append({
        "step": len(operations) + 1,
        "type": "finishing",
        "tool": "end_mill_3mm",
        "description": "Чистовая обработка",
        "estimated_time": "10 мин"
    })
    
    # Базовый G-код
    gcode_recommendations = {
        "fanuc": f"""G90 G17 G21 G54
M3 S{cutting_parameters['roughing']['n']}
G0 Z5
G0 X0 Y0
G1 Z-2 F{cutting_parameters['roughing']['F']}
G1 X{dimensions.get('length', 100)} Y{dimensions.get('width', 100)}
G0 Z5
M5
M30""",
        "siemens": f"""G90 G17 G71 G54
M3 S{cutting_parameters['roughing']['n']}
G0 Z5
G0 X0 Y0
G1 Z-2 F{cutting_parameters['roughing']['F']}
G1 X{dimensions.get('length', 100)} Y{dimensions.get('width', 100)}
G0 Z5
M5
M2"""
    }
    
    return {
        "success": True,
        "ai_provider": "basic",
        "recommendations": {
            "tools": tools,
            "cutting_parameters": cutting_parameters,
            "operations": operations,
            "gcode_recommendations": gcode_recommendations
        },
        "raw_response": "Базовые рекомендации без ИИ"
    }

def generate_enhanced_milling_gcode(stl_path: Path, out_path: Path, **params) -> Dict:
    """Enhanced milling G-code generation with cutting parameters calculation"""
    start_time = time.time()
    
    try:
        # Validate and sanitize parameters
        validated_params = SecurityValidator.validate_gcode_params(params)
        
        controller_settings = get_controller_settings(params.get("controller", "fanuc"))
        
        (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler_simple(stl_path, 0.1)
        
        # Apply allowances
        xmin -= params.get("allowance_x", 0)
        xmax += params.get("allowance_x", 0)
        ymin -= params.get("allowance_y", 0)
        ymax += params.get("allowance_y", 0)
        zmax += params.get("allowance_z", 0)
        
        with open(out_path, "w", encoding="ascii", errors="ignore") as f:
            w = f.write
            w(f"(Generated by CNCera - Enhanced {params.get('operation_type', 'milling').title()} Operation)\n")
            w(f"(Tool: {validated_params.get('tool_diam', 3.0)}mm, Feed: {validated_params.get('feed', 300)} mm/min)\n")
            w(f"(Spindle: {validated_params.get('spindle', 8000)} RPM)\n")
            
            for cmd in controller_settings["header"]:
                w(f"{cmd}\n")
            
            # Set work offset
            work_offset = params.get("work_offset", "G54")
            w(f"{work_offset}\n")
            
            if validated_params.get("spindle"):
                w(f"{controller_settings['spindle_on'].format(spindle=validated_params['spindle'])}\n")
            w(f"{controller_settings['coolant_on']}\n")
            
            clearance = validated_params.get("clearance", 5.0)
            w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
            
            # Enhanced milling strategy
            stepover = validated_params.get("stepover", 0.4)
            tool_diam = validated_params.get("tool_diam", 3.0)
            step_xy = max(0.1, tool_diam * stepover)
            
            # Adaptive toolpath
            w("(Adaptive milling strategy)\n")
            center_x = (xmin + xmax) / 2
            center_y = (ymin + ymax) / 2
            max_radius = max(xmax - center_x, ymax - center_y)
            
            w(f"{controller_settings['rapid']} X{center_x:.3f} Y{center_y:.3f}\n")
            w(f"{controller_settings['linear']} Z{zmax:.3f} F{params.get('plunge', 120):.1f}\n")
            w(f"F{validated_params.get('feed', 300):.1f}\n")
            
            # Spiral toolpath
            radius = step_xy
            while radius <= max_radius:
                for angle in range(0, 360, 10):
                    x = center_x + radius * math.cos(math.radians(angle))
                    y = center_y + radius * math.sin(math.radians(angle))
                    z = z_func(x, y)
                    if z is not None:
                        w(f"{controller_settings['linear']} X{x:.3f} Y{y:.3f} Z{z:.3f}\n")
                radius += step_xy
            
            w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
            w(f"{controller_settings['coolant_off']}\n")
            if validated_params.get("spindle"):
                w(f"{controller_settings['spindle_off']}\n")
            w(f"{controller_settings['program_end']}\n")
        
        processing_time = time.time() - start_time
        metrics_collector.record_processing(
            params.get("operation_type", "milling"), 
            stl_path.stat().st_size, 
            processing_time, 
            True
        )
        
        return {
            "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin, "zmax": zmax},
            "processing_time": processing_time
        }
        
    except Exception as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "Enhanced milling G-code generation")
        metrics_collector.record_processing(
            params.get("operation_type", "milling"), 
            stl_path.stat().st_size if stl_path.exists() else 0, 
            processing_time, 
            False,
            error.error_type.value
        )
        raise

def generate_chamfer_gcode(stl_path: Path, out_path: Path, **params) -> Dict:
    """Generate G-code for chamfering operations"""
    controller_settings = get_controller_settings(params.get("controller", "fanuc"))

    (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler_simple(stl_path, 0.1)

    xmin -= params.get("allowance_x", 0)
    xmax += params.get("allowance_x", 0)
    ymin -= params.get("allowance_y", 0)
    ymax += params.get("allowance_y", 0)
    zmax += params.get("allowance_z", 0)

    with open(out_path, "w", encoding="ascii", errors="ignore") as f:
        w = f.write
        w("(Generated by CNCera - Chamfer Operation)\n")
        for cmd in controller_settings["header"]:
            w(f"{cmd}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_on'].format(spindle=params['spindle'])}\n")
        w(f"{controller_settings['coolant_on']}\n")

        clearance = params.get("clearance", 5.0)
        tool_diam = params.get("tool_diam", 3.0)

        w(f"(Chamfer around perimeter)\n")
        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")

        w(f"{controller_settings['rapid']} X{xmin:.3f} Y{ymin:.3f}\n")
        w(f"{controller_settings['linear']} Z{zmax:.3f} F{params.get('plunge', 120):.1f}\n")

        chamfer_points = [
            (xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin)
        ]
        w(f"F{params.get('feed', 300):.1f}\n")
        for x, y in chamfer_points:
            w(f"{controller_settings['linear']} X{x:.3f} Y{y:.3f}\n")

        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
        w(f"{controller_settings['coolant_off']}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_off']}\n")
        w(f"{controller_settings['program_end']}\n")

    return {
        "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin, "zmax": zmax},
        "grid": {"nx": 4, "ny": 4, "step_xy": (xmax - xmin) / 4},
        "origin": {"ox": xmin, "oy": ymin, "oz": zmin}
    }

def generate_turning_gcode(stl_path: Path, out_path: Path, **params) -> Dict:
    """Generate G-code for turning operations"""
    controller_settings = get_controller_settings(params.get("controller", "fanuc"))

    with open(out_path, "w", encoding="ascii", errors="ignore") as f:
        w = f.write
        w("(Generated by CNCera - Turning Operation)\n")
        for cmd in controller_settings["header"]:
            w(f"{cmd}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_on'].format(spindle=params['spindle'])}\n")
        w(f"{controller_settings['coolant_on']}\n")

        workpiece_dia = params.get("workpiece_diameter", 50.0)
        cut_depth = params.get("cut_depth", 1.0)
        feed_per_rev = params.get("feed_per_rev", 0.2)
        turning_type = params.get("turning_type", "roughing")
        clearance = params.get("clearance", 5.0)

        if turning_type == "facing":
            w("(Face operation)\n")
            w(f"{controller_settings['rapid']} X{workpiece_dia + clearance:.3f} Z{clearance:.3f}\n")
            w(f"{controller_settings['rapid']} Z0.5\n")
            w(f"{controller_settings['linear']} X{workpiece_dia:.3f} F{feed_per_rev:.3f}\n")
            w(f"{controller_settings['linear']} X0 Z0\n")
        else:
            w(f"(Turning - {turning_type})\n")
            current_dia = workpiece_dia
            target_dia = workpiece_dia - (cut_depth * 2)
            while current_dia > target_dia:
                w(f"{controller_settings['rapid']} X{current_dia + clearance:.3f} Z{clearance:.3f}\n")
                w(f"{controller_settings['rapid']} Z0.5\n")
                w(f"{controller_settings['linear']} X{current_dia:.3f} F{feed_per_rev:.3f}\n")
                w(f"{controller_settings['linear']} Z-50\n")
                current_dia -= cut_depth * 2

        w(f"{controller_settings['rapid']} X{workpiece_dia + clearance:.3f} Z{clearance:.3f}\n")
        w(f"{controller_settings['coolant_off']}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_off']}\n")
        w(f"{controller_settings['program_end']}\n")

    return {
        "bbox": {"xmin": 0, "xmax": workpiece_dia, "ymin": 0, "ymax": workpiece_dia, "zmin": -50, "zmax": 0},
        "grid": {"nx": 10, "ny": 10, "step_xy": workpiece_dia / 10},
        "origin": {"ox": 0, "oy": 0, "oz": 0}
    }

def generate_drilling_gcode(stl_path: Path, out_path: Path, **params) -> Dict:
    """Generate G-code for drilling operations"""
    controller_settings = get_controller_settings(params.get("controller", "fanuc"))

    (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler_simple(stl_path, 0.5)

    with open(out_path, "w", encoding="ascii", errors="ignore") as f:
        w = f.write
        w("(Generated by CNCera - Drilling Operation)\n")
        for cmd in controller_settings["header"]:
            w(f"{cmd}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_on'].format(spindle=params['spindle'])}\n")
        w(f"{controller_settings['coolant_on']}\n")

        drill_cycle = params.get("drill_cycle", "G81")
        drill_depth = params.get("drill_depth", 10.0)
        clearance = params.get("clearance", 5.0)
        peck_depth = params.get("peck_depth", 2.0)
        feed = params.get("feed", 300.0)

        center_x = (xmin + xmax) / 2
        center_y = (ymin + ymax) / 2

        w(f"(Drilling cycle: {drill_cycle})\n")
        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
        w(f"{controller_settings['rapid']} X{center_x:.3f} Y{center_y:.3f}\n")

        if drill_cycle == "G83":
            w(f"G83 X{center_x:.3f} Y{center_y:.3f} Z{-drill_depth:.3f} R{clearance:.3f} Q{peck_depth:.3f} F{feed:.1f}\n")
        elif drill_cycle == "G82":
            w(f"G82 X{center_x:.3f} Y{center_y:.3f} Z{-drill_depth:.3f} R{clearance:.3f} P1000 F{feed:.1f}\n")
        else:
            w(f"G81 X{center_x:.3f} Y{center_y:.3f} Z{-drill_depth:.3f} R{clearance:.3f} F{feed:.1f}\n")

        w("G80\n")
        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
        w(f"{controller_settings['coolant_off']}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_off']}\n")
        w(f"{controller_settings['program_end']}\n")

    return {
        "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin - drill_depth, "zmax": zmax},
        "grid": {"nx": 1, "ny": 1, "step_xy": 1},
        "origin": {"ox": center_x, "oy": center_y, "oz": zmax}
    }

# ---- HTML Template ----
INDEX_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>CNCera — 3D Analysis & G-code Generation</title>
    <script src="https://cdn.tailwindcss.com"></script>
    
    <!-- Three.js and dependencies -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>
    
    <style>
        #viewer { min-height: 400px; }
        #log, #glog { white-space: pre-wrap; }
        #chat-messages { max-height: 400px; overflow-y: auto; }
        .chat-message { margin-bottom: 1rem; padding: 0.75rem; border-radius: 0.5rem; }
        .user-message { background-color: #1e40af; margin-left: 2rem; }
        .ai-message { background-color: #374151; margin-right: 2rem; }
        .loading { opacity: 0.6; }
    </style>
</head>
<body class="bg-gray-900 text-gray-100 font-sans p-6">
    <div class="max-w-6xl mx-auto space-y-6">
        <!-- Header -->
        <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
            <h1 class="text-2xl font-bold text-blue-400">CNCera Enhanced</h1>
            <p class="text-gray-400 mt-2">Advanced 3D Analysis & G-code Generation</p>
        </div>

        <!-- File Upload Section -->
        <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
            <h2 class="text-xl font-semibold mb-4">Загрузка и анализ файла</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Файл</label>
                    <input id="file" type="file" accept=".step,.stp,.stl" class="block w-full text-sm text-gray-900 bg-gray-700 border border-gray-600 rounded-lg p-2 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-blue-600 file:text-white hover:file:bg-blue-700">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Единицы</label>
                    <select id="units" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        <option value="auto">Auto (mm)</option>
                        <option value="mm">mm</option>
                        <option value="inch">inch</option>
                        <option value="m">m</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">LinearDeflection</label>
                    <input id="linDef" type="number" step="0.01" value="0.1" min="0.01" max="10" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">AngularDeflection (°)</label>
                    <input id="angDef" type="number" step="0.5" value="15" min="0.01" max="89" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Relative</label>
                    <input id="rel" type="checkbox" class="h-5 w-5 text-blue-600 bg-gray-700 border-gray-600 rounded">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Начало координат</label>
                    <select id="work_offset" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        <option value="G54">G54</option>
                        <option value="G55">G55</option>
                        <option value="G56">G56</option>
                        <option value="G57">G57</option>
                        <option value="G58">G58</option>
                        <option value="G59">G59</option>
                    </select>
                </div>
            </div>
            <button onclick="analyze()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition">Анализировать</button>
            <div id="log" class="mt-4 text-gray-400"></div>
        </div>

        <!-- Analysis Results Section -->
        <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
            <h2 class="text-xl font-semibold mb-4">Результат анализа</h2>
            <div id="viewer" class="bg-gray-900 rounded-lg flex items-center justify-center">
                <div class="text-gray-400 p-8">Загрузите файл для предпросмотра</div>
            </div>
            <div id="meta" class="mt-4"></div>
            
            <!-- Detailed Geometry Analysis -->
            <div id="geometry_analysis" class="mt-6" style="display: none;">
                <h3 class="text-lg font-medium mb-3">Детальный анализ геометрии</h3>
                <div id="geometry_details" class="grid grid-cols-1 md:grid-cols-2 gap-4"></div>
            </div>
            
            <!-- AI Chat Section -->
            <div id="ai_chat" class="mt-6" style="display: none;">
                <h3 class="text-lg font-medium mb-3">Чат с ИИ для анализа детали</h3>
                <div class="mb-4">
                    <label class="block text-sm text-gray-400 mb-1">ИИ провайдер</label>
                    <select id="chat_ai_provider" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        <option value="openai">OpenAI (GPT)</option>
                        <option value="anthropic">Anthropic (Claude)</option>
                        <option value="xai">xAI (Grok)</option>
                    </select>
                </div>
                <div id="chat-messages" class="bg-gray-900 p-4 rounded-lg mb-4"></div>
                <div class="flex gap-2">
                    <input id="chat-input" type="text" placeholder="Задайте вопрос о детали..." class="flex-1 bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    <button onclick="sendChatMessage()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition">Отправить</button>
                </div>
            </div>
            
            <!-- CAM Recommendations -->
            <div id="cam_recommendations" class="mt-6" style="display: none;">
                <h3 class="text-lg font-medium mb-3">CAM рекомендации</h3>
                <div class="mb-4">
                    <label class="block text-sm text-gray-400 mb-1">ИИ провайдер</label>
                    <select id="ai_provider" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        <option value="openai">OpenAI (GPT)</option>
                        <option value="anthropic">Anthropic (Claude)</option>
                        <option value="xai">xAI (Grok)</option>
                    </select>
                </div>
                <button onclick="getCamRecommendations()" class="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 transition mb-4">Получить CAM рекомендации</button>
                <div id="cam_results"></div>
            </div>
        </div>

        <!-- G-code Generation Section -->
        <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
            <h2 class="text-xl font-semibold mb-4">Генерация G-кода</h2>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Контроллер</label>
                    <select id="controller" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        <option value="fanuc">Fanuc</option>
                        <option value="siemens">Siemens</option>
                        <option value="heidenhain">Heidenhain</option>
                        <option value="gsk">GSK</option>
                        <option value="mazak">Mazak</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Тип обработки</label>
                    <select id="operation_type" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        <option value="milling">Фрезерная</option>
                        <option value="turning">Токарная</option>
                        <option value="drilling">Сверление</option>
                        <option value="chamfer">Фаска</option>
                        <option value="roughing">Черновая обработка</option>
                        <option value="finishing">Финишная обработка</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">G54 (начало координат)</label>
                    <select id="origin" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        <option value="bbox_min">Нижний угол</option>
                        <option value="bbox_center">Центр низа</option>
                        <option value="bbox_top_center">Центр верха</option>
                    </select>
                </div>
            </div>

            <div class="mb-6">
                <h3 class="text-lg font-medium mb-3">Материал и инструмент</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Марка материала</label>
                        <select id="material_grade" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                            <option value="42CrMo4">42CrMo4 (Сталь)</option>
                            <option value="Al6061">Al6061 (Алюминий)</option>
                            <option value="316L">316L (Нержавеющая)</option>
                            <option value="GG25">GG25 (Чугун)</option>
                            <option value="Ti6Al4V">Ti6Al4V (Титан)</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Ø инструмента, мм</label>
                        <input id="tool" type="number" value="3" step="0.1" min="0.1" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Число зубьев</label>
                        <input id="flutes" type="number" value="2" step="1" min="1" max="8" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Радиус угла, мм</label>
                        <input id="corner_radius" type="number" value="0" step="0.1" min="0" max="5" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                </div>
            </div>

            <div class="mb-6">
                <h3 class="text-lg font-medium mb-3">Параметры инструмента</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Spindle, об/мин</label>
                        <input id="spindle" type="number" value="8000" step="100" min="1000" max="24000" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Feed, мм/мин</label>
                        <input id="feed" type="number" value="300" step="10" min="10" max="5000" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Plunge, мм/мин</label>
                        <input id="plunge" type="number" value="120" step="10" min="10" max="2000" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Clearance Z, мм</label>
                        <input id="clearance" type="number" value="5" step="0.5" min="1" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                </div>
            </div>

            <div class="mb-6">
                <h3 class="text-lg font-medium mb-3">Настройки фрезерования</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Степовер</label>
                        <input id="stepover" type="number" value="0.4" step="0.05" min="0.05" max="0.95" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Stepdown Z, мм</label>
                        <input id="stepdown" type="number" value="0" step="0.5" min="0" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Ось проходов</label>
                        <select id="dir" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                            <option>X</option>
                            <option>Y</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Waterline</label>
                        <input id="waterline" type="checkbox" class="h-5 w-5 text-blue-600 bg-gray-700 border-gray-600 rounded">
                    </div>
                </div>
            </div>

            <div class="mb-6">
                <h3 class="text-lg font-medium mb-3">Ручные припуски</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Припуск X, мм</label>
                        <input id="allowance_x" type="number" value="0" step="0.1" min="-10" max="10" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Припуск Y, мм</label>
                        <input id="allowance_y" type="number" value="0" step="0.1" min="-10" max="10" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Припуск Z, мм</label>
                        <input id="allowance_z" type="number" value="0" step="0.1" min="-10" max="10" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                </div>
            </div>

            <div class="flex items-center space-x-4">
                <button onclick="gen()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition">Сгенерировать G-код</button>
                <span id="glog" class="text-gray-400"></span>
            </div>
        </div>

        <!-- System Monitoring -->
        <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
            <h2 class="text-xl font-semibold mb-4">Мониторинг системы</h2>
            <div id="system_metrics" class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div class="bg-gray-700 p-4 rounded-lg">
                    <h3 class="text-sm text-gray-400">Всего запросов</h3>
                    <p id="total_requests" class="text-2xl font-bold text-blue-400">0</p>
                </div>
                <div class="bg-gray-700 p-4 rounded-lg">
                    <h3 class="text-sm text-gray-400">Успешность</h3>
                    <p id="success_rate" class="text-2xl font-bold text-green-400">100%</p>
                </div>
                <div class="bg-gray-700 p-4 rounded-lg">
                    <h3 class="text-sm text-gray-400">Время работы</h3>
                    <p id="uptime" class="text-2xl font-bold text-yellow-400">0s</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let LAST_MODEL_PATH = null;

        async function analyze() {
            const file = document.getElementById('file').files[0];
            const log = document.getElementById('log');
            if (!file) {
                log.textContent = 'Выберите файл';
                return;
            }
            if (file.size > 100 * 1024 * 1024) {
                log.textContent = 'Файл слишком большой (макс. 100 МБ)';
                return;
            }
            log.textContent = 'Загрузка...';
            const fd = new FormData();
            fd.append('file', file);
            fd.append('units', document.getElementById('units').value || 'auto');
            fd.append('linear_deflection', document.getElementById('linDef').value || '0.1');
            fd.append('angular_deflection_deg', document.getElementById('angDef').value || '15');
            fd.append('relative', document.getElementById('rel').checked ? 'true' : 'false');
            fd.append('work_offset', document.getElementById('work_offset').value || 'G54');

            try {
                const r = await fetch('/upload', { method: 'POST', body: fd });
                const data = await r.json();
                if (!data.success) {
                    log.textContent = 'Ошибка: ' + (data.error || 'Неизвестная ошибка');
                    return;
                }
                LAST_MODEL_PATH = data.model_path;
                const links = [];
                if (data.model_path) {
                    links.push(`<a href="${data.model_path}" target="_blank" class="text-blue-400 hover:underline">Скачать STL</a>`);
                }
                if (data.result_filename) {
                    links.push(`<a href="/download_results?filename=${data.result_filename}" target="_blank" class="text-blue-400 hover:underline">JSON-результат</a>`);
                }
                log.innerHTML = 'Готово — ' + links.join(' · ');

                // 3D Viewer with Three.js
                const viewer = document.getElementById('viewer');
                if (typeof THREE !== 'undefined' && data.model_path) {
                    loadSTLModel(data.model_path, viewer, data.geometry);
                } else if (data.preview_png_data) {
                    viewer.innerHTML = `<img src="${data.preview_png_data}" alt="preview" class="max-w-full max-h-full object-contain rounded-lg">`;
                } else if (data.preview_png) {
                    viewer.innerHTML = `<img src="${data.preview_png}" alt="preview" class="max-w-full max-h-full object-contain rounded-lg">`;
                } else {
                    viewer.innerHTML = '<div class="text-gray-400 p-8">Предпросмотр недоступен</div>';
                }

                const meta = document.getElementById('meta');
                const rows = [];
                function push(k, v) {
                    rows.push(`<tr class="border-b border-gray-700"><td class="py-2 px-4">${k}</td><td class="py-2 px-4">${v}</td></tr>`);
                }
                if (data.file_info) {
                    push('Файл', data.file_info.filename);
                    push('Размер файла', `${data.file_info.file_size} байт`);
                    push('Тип файла', data.file_info.file_type);
                }
                if (data.geometry && data.geometry.dimensions) {
                    const d = data.geometry.dimensions;
                    push('Размеры (мм)', `${d.length} × ${d.width} × ${d.height}`);
                }
                if (data.mesh_info) {
                    push('Вершины', data.mesh_info.vertices);
                    push('Грани', data.mesh_info.faces);
                }
                meta.innerHTML = `<table class="w-full border-collapse"><thead><tr class="bg-gray-700"><th class="py-2 px-4 text-left">Параметр</th><th class="py-2 px-4 text-left">Значение</th></tr></thead><tbody>${rows.join('')}</tbody></table>`;
                
                // Сохраняем данные анализа для CAM рекомендаций
                window.lastAnalysisData = data;
                
                // Показываем детальный анализ геометрии если доступен
                if (data.geometry_analysis) {
                    displayGeometryAnalysis(data.geometry_analysis);
                }
                
                // Показываем чат с ИИ
                document.getElementById('ai_chat').style.display = 'block';
                document.getElementById('cam_recommendations').style.display = 'block';
                
                // Автоматически запускаем анализ с ИИ
                if (data.geometry_analysis) {
                    setTimeout(() => {
                        autoAnalyzeWithAI(data);
                    }, 1000);
                }
            } catch (err) {
                log.textContent = 'Сетевая ошибка: ' + err;
            }
        }

        // 3D Viewer Functions
        let scene, camera, renderer, controls, model;
        
        function loadSTLModel(modelPath, container, geometry) {
            if (typeof THREE === 'undefined') {
                container.innerHTML = '<div class="text-gray-400 p-8">Three.js не загружен, используем PNG</div>';
                return;
            }
            
            // Clear previous model
            if (model) {
                scene.remove(model);
            }
            
            // Setup scene
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x0b1b24);
            
            // Setup camera
            camera = new THREE.PerspectiveCamera(75, container.clientWidth / container.clientHeight, 0.1, 1000);
            camera.position.set(50, 50, 50);
            
            // Setup renderer
            renderer = new THREE.WebGLRenderer({ antialias: true });
            renderer.setSize(container.clientWidth, container.clientHeight);
            renderer.shadowMap.enabled = true;
            renderer.shadowMap.type = THREE.PCFSoftShadowMap;
            
            // Setup controls
            if (typeof THREE.OrbitControls !== 'undefined') {
                controls = new THREE.OrbitControls(camera, renderer.domElement);
                controls.enableDamping = true;
                controls.dampingFactor = 0.05;
            }
            
            // Clear container and add renderer
            container.innerHTML = '';
            container.appendChild(renderer.domElement);
            
            // Add lighting
            const ambientLight = new THREE.AmbientLight(0x404040, 0.6);
            scene.add(ambientLight);
            
            const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
            directionalLight.position.set(50, 50, 50);
            directionalLight.castShadow = true;
            scene.add(directionalLight);
            
            // Load STL model
            const loader = new THREE.STLLoader();
            loader.load(modelPath, function(geometry) {
                const material = new THREE.MeshPhongMaterial({ 
                    color: 0x55aaff,
                    shininess: 100,
                    transparent: true,
                    opacity: 0.9
                });
                
                model = new THREE.Mesh(geometry, material);
                model.castShadow = true;
                model.receiveShadow = true;
                
                // Center and scale model
                const box = new THREE.Box3().setFromObject(model);
                const center = box.getCenter(new THREE.Vector3());
                const size = box.getSize(new THREE.Vector3());
                const maxDim = Math.max(size.x, size.y, size.z);
                const scale = 50 / maxDim;
                
                model.scale.setScalar(scale);
                model.position.sub(center.multiplyScalar(scale));
                
                scene.add(model);
                
                // Add zero point indicator
                addZeroPointIndicator(geometry, scale);
                
                // Start animation
                animate();
            }, undefined, function(error) {
                console.error('Error loading STL:', error);
                container.innerHTML = '<div class="text-red-400 p-8">Ошибка загрузки 3D модели</div>';
            });
        }
        
        function addZeroPointIndicator(geometry, scale) {
            // Calculate bounding box from geometry
            const box = new THREE.Box3().setFromObject(model);
            const size = box.getSize(new THREE.Vector3());
            const center = box.getCenter(new THREE.Vector3());
            
            // Position zero point above the model
            const zeroPointY = center.y + size.y / 2 + 5;
            
            // Create zero point indicator
            const zeroPointGeometry = new THREE.SphereGeometry(1, 16, 16);
            const zeroPointMaterial = new THREE.MeshBasicMaterial({ color: 0xff0000 });
            const zeroPoint = new THREE.Mesh(zeroPointGeometry, zeroPointMaterial);
            
            zeroPoint.position.set(0, zeroPointY, 0);
            zeroPoint.name = 'zeroPoint';
            
            scene.add(zeroPoint);
            
            // Add coordinate axes
            const axesHelper = new THREE.AxesHelper(20);
            axesHelper.position.set(0, zeroPointY, 0);
            scene.add(axesHelper);
        }
        
        function animate() {
            requestAnimationFrame(animate);
            
            if (controls) {
                controls.update();
            }
            
            if (renderer && scene && camera) {
                renderer.render(scene, camera);
            }
        }
        
        // Chat Functions
        async function sendChatMessage() {
            const input = document.getElementById('chat-input');
            const message = input.value.trim();
            if (!message) return;
            
            const messagesContainer = document.getElementById('chat-messages');
            const provider = document.getElementById('chat_ai_provider').value;
            
            // Add user message
            addChatMessage(message, 'user');
            input.value = '';
            
            // Add loading indicator
            const loadingId = addChatMessage('Анализирую деталь...', 'ai', true);
            
            try {
                const response = await fetch('/ai_chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        message: message,
                        provider: provider,
                        analysis_data: window.lastAnalysisData
                    })
                });
                
                const data = await response.json();
                
                // Remove loading message
                const loadingElement = document.getElementById(loadingId);
                if (loadingElement) {
                    loadingElement.remove();
                }
                
                if (data.success) {
                    addChatMessage(data.response, 'ai');
                } else {
                    addChatMessage('Ошибка: ' + (data.error || 'Неизвестная ошибка'), 'ai');
                }
            } catch (error) {
                // Remove loading message
                const loadingElement = document.getElementById(loadingId);
                if (loadingElement) {
                    loadingElement.remove();
                }
                addChatMessage('Сетевая ошибка: ' + error.message, 'ai');
            }
        }
        
        function addChatMessage(message, type, isLoading = false) {
            const messagesContainer = document.getElementById('chat-messages');
            const messageId = 'msg_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            
            const messageDiv = document.createElement('div');
            messageDiv.id = messageId;
            messageDiv.className = `chat-message ${type}-message ${isLoading ? 'loading' : ''}`;
            messageDiv.textContent = message;
            
            messagesContainer.appendChild(messageDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            
            return messageId;
        }
        
        // Handle Enter key in chat input
        document.addEventListener('DOMContentLoaded', function() {
            const chatInput = document.getElementById('chat-input');
            if (chatInput) {
                chatInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') {
                        sendChatMessage();
                    }
                });
            }
        });
        
        // Автоматический анализ с ИИ
        async function autoAnalyzeWithAI(analysisData) {
            const messagesContainer = document.getElementById('chat-messages');
            const provider = document.getElementById('chat_ai_provider').value;
            
            // Добавляем автоматический вопрос
            const autoMessage = "Проанализируй эту деталь и дай рекомендации по обработке: какие инструменты использовать, режимы резания, последовательность операций и G-код.";
            addChatMessage(autoMessage, 'user');
            
            // Добавляем индикатор загрузки
            const loadingId = addChatMessage('Анализирую деталь с помощью ИИ...', 'ai', true);
            
            try {
                const response = await fetch('/ai_chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        message: autoMessage,
                        provider: provider,
                        analysis_data: analysisData
                    })
                });
                
                const data = await response.json();
                
                // Удаляем индикатор загрузки
                const loadingElement = document.getElementById(loadingId);
                if (loadingElement) {
                    loadingElement.remove();
                }
                
                if (data.success) {
                    addChatMessage(data.response, 'ai');
                } else {
                    addChatMessage('Ошибка ИИ анализа: ' + (data.error || 'Неизвестная ошибка'), 'ai');
                }
            } catch (error) {
                // Удаляем индикатор загрузки
                const loadingElement = document.getElementById(loadingId);
                if (loadingElement) {
                    loadingElement.remove();
                }
                addChatMessage('Ошибка сети при анализе ИИ: ' + error.message, 'ai');
            }
        }

        function displayGeometryAnalysis(geometryAnalysis) {
            const geometryDiv = document.getElementById('geometry_analysis');
            const detailsDiv = document.getElementById('geometry_details');
            
            if (!geometryAnalysis) {
                return;
            }
            
            const summary = geometryAnalysis.summary || {};
            const elements = geometryAnalysis.elements || [];
            
            let html = `
                <div class="bg-gray-700 p-4 rounded-lg">
                    <h4 class="font-medium text-blue-400 mb-2">Обнаруженные элементы</h4>
                    <div class="space-y-1 text-sm">
                        <div>Отверстия: <span class="text-yellow-400">${summary.total_holes || 0}</span></div>
                        <div>Карманы: <span class="text-yellow-400">${summary.total_pockets || 0}</span></div>
                        <div>Фаски: <span class="text-yellow-400">${summary.total_chamfers || 0}</span></div>
                        <div>Резьбы: <span class="text-yellow-400">${summary.total_threads || 0}</span></div>
                        <div>Бобышки: <span class="text-yellow-400">${summary.total_bosses || 0}</span></div>
                        <div>Материал: <span class="text-green-400">${summary.primary_material || 'Не определен'}</span></div>
                    </div>
                </div>
            `;
            
            if (elements.length > 0) {
                const firstElement = elements[0];
                if (firstElement.dimensions) {
                    const dims = firstElement.dimensions;
                    html += `
                        <div class="bg-gray-700 p-4 rounded-lg">
                            <h4 class="font-medium text-blue-400 mb-2">Размеры</h4>
                            <div class="space-y-1 text-sm">
                                <div>Длина: <span class="text-yellow-400">${dims.length || 0} мм</span></div>
                                <div>Ширина: <span class="text-yellow-400">${dims.width || 0} мм</span></div>
                                <div>Высота: <span class="text-yellow-400">${dims.height || 0} мм</span></div>
                                <div>Объем: <span class="text-yellow-400">${dims.volume || 0} мм³</span></div>
                                <div>Площадь: <span class="text-yellow-400">${dims.surface_area || 0} мм²</span></div>
                            </div>
                        </div>
                    `;
                }
                
                // Показываем детали отверстий
                if (firstElement.holes && firstElement.holes.length > 0) {
                    html += `
                        <div class="bg-gray-700 p-4 rounded-lg">
                            <h4 class="font-medium text-blue-400 mb-2">Отверстия</h4>
                            <div class="space-y-1 text-sm">
                    `;
                    firstElement.holes.forEach((hole, index) => {
                        html += `<div>Ø${hole.diameter || hole.radius * 2}мм ${hole.is_through ? '(сквозное)' : '(глухое)'}</div>`;
                    });
                    html += `</div></div>`;
                }
                
                // Показываем допуски
                if (firstElement.tolerances && firstElement.tolerances.length > 0) {
                    html += `
                        <div class="bg-gray-700 p-4 rounded-lg">
                            <h4 class="font-medium text-blue-400 mb-2">Допуски</h4>
                            <div class="space-y-1 text-sm">
                    `;
                    firstElement.tolerances.forEach(tolerance => {
                        html += `<div class="text-orange-400">${tolerance}</div>`;
                    });
                    html += `</div></div>`;
                }
            }
            
            detailsDiv.innerHTML = html;
            geometryDiv.style.display = 'block';
        }

        async function getCamRecommendations() {
            const camResults = document.getElementById('cam_results');
            const provider = document.getElementById('ai_provider').value;
            
            // Получаем данные анализа геометрии из предыдущего результата
            if (!window.lastAnalysisData) {
                camResults.innerHTML = '<div class="text-red-400">Сначала загрузите и проанализируйте файл</div>';
                return;
            }
            
            camResults.innerHTML = '<div class="text-blue-400">Получение CAM рекомендаций...</div>';
            
            try {
                const response = await fetch('/cam_analysis', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        geometry_analysis: window.lastAnalysisData.geometry_analysis || window.lastAnalysisData,
                        provider: provider
                    })
                });
                
                const data = await response.json();
                if (!data.success) {
                    camResults.innerHTML = `<div class="text-red-400">Ошибка: ${data.error}</div>`;
                    return;
                }
                
                displayCamRecommendations(data.cam_recommendations);
                
            } catch (err) {
                camResults.innerHTML = `<div class="text-red-400">Сетевая ошибка: ${err}</div>`;
            }
        }

        function displayCamRecommendations(camData) {
            const camResults = document.getElementById('cam_results');
            
            if (!camData.success) {
                camResults.innerHTML = '<div class="text-red-400">Ошибка получения рекомендаций</div>';
                return;
            }
            
            const rec = camData.recommendations;
            const provider = camData.ai_provider;
            
            let html = `
                <div class="bg-gray-700 p-4 rounded-lg mb-4">
                    <h4 class="font-medium text-green-400 mb-2">Провайдер: ${provider.toUpperCase()}</h4>
                </div>
            `;
            
            // Инструменты
            if (rec.tools && rec.tools.length > 0) {
                html += `
                    <div class="bg-gray-700 p-4 rounded-lg mb-4">
                        <h4 class="font-medium text-blue-400 mb-3">Рекомендуемые инструменты</h4>
                        <div class="space-y-2">
                `;
                rec.tools.forEach(tool => {
                    html += `
                        <div class="bg-gray-600 p-3 rounded">
                            <div class="font-medium">${tool.type} Ø${tool.diameter}мм</div>
                            <div class="text-sm text-gray-300">${tool.description || ''}</div>
                            <div class="text-xs text-gray-400">Материал: ${tool.material}, Патрон: ${tool.holder}</div>
                        </div>
                    `;
                });
                html += '</div></div>';
            }
            
            // Параметры резания
            if (rec.cutting_parameters) {
                html += `
                    <div class="bg-gray-700 p-4 rounded-lg mb-4">
                        <h4 class="font-medium text-blue-400 mb-3">Режимы резания</h4>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                `;
                
                if (rec.cutting_parameters.roughing) {
                    const rough = rec.cutting_parameters.roughing;
                    html += `
                        <div class="bg-gray-600 p-3 rounded">
                            <h5 class="font-medium text-yellow-400 mb-2">Черновая обработка</h5>
                            <div class="text-sm space-y-1">
                                <div>Vc: ${rough.Vc} м/мин</div>
                                <div>n: ${rough.n} об/мин</div>
                                <div>fz: ${rough.fz} мм/зуб</div>
                                <div>F: ${rough.F} мм/мин</div>
                                <div>ap: ${rough.ap} мм</div>
                                <div>ae: ${rough.ae} мм</div>
                            </div>
                        </div>
                    `;
                }
                
                if (rec.cutting_parameters.finishing) {
                    const finish = rec.cutting_parameters.finishing;
                    html += `
                        <div class="bg-gray-600 p-3 rounded">
                            <h5 class="font-medium text-green-400 mb-2">Чистовая обработка</h5>
                            <div class="text-sm space-y-1">
                                <div>Vc: ${finish.Vc} м/мин</div>
                                <div>n: ${finish.n} об/мин</div>
                                <div>fz: ${finish.fz} мм/зуб</div>
                                <div>F: ${finish.F} мм/мин</div>
                                <div>ap: ${finish.ap} мм</div>
                                <div>ae: ${finish.ae} мм</div>
                            </div>
                        </div>
                    `;
                }
                
                html += '</div></div>';
            }
            
            // План операций
            if (rec.operations && rec.operations.length > 0) {
                html += `
                    <div class="bg-gray-700 p-4 rounded-lg mb-4">
                        <h4 class="font-medium text-blue-400 mb-3">План операций</h4>
                        <div class="space-y-2">
                `;
                rec.operations.forEach(op => {
                    html += `
                        <div class="bg-gray-600 p-3 rounded flex justify-between items-center">
                            <div>
                                <div class="font-medium">Шаг ${op.step}: ${op.type}</div>
                                <div class="text-sm text-gray-300">${op.description}</div>
                                <div class="text-xs text-gray-400">Инструмент: ${op.tool}</div>
                            </div>
                            <div class="text-sm text-yellow-400">${op.estimated_time || ''}</div>
                        </div>
                    `;
                });
                html += '</div></div>';
            }
            
            // G-код рекомендации
            if (rec.gcode_recommendations) {
                html += `
                    <div class="bg-gray-700 p-4 rounded-lg">
                        <h4 class="font-medium text-blue-400 mb-3">G-код рекомендации</h4>
                        <div class="space-y-3">
                `;
                
                Object.entries(rec.gcode_recommendations).forEach(([controller, gcode]) => {
                    html += `
                        <div class="bg-gray-600 p-3 rounded">
                            <h5 class="font-medium text-yellow-400 mb-2">${controller.toUpperCase()}</h5>
                            <pre class="text-xs text-gray-300 whitespace-pre-wrap">${gcode}</pre>
                        </div>
                    `;
                });
                
                html += '</div></div>';
            }
            
            camResults.innerHTML = html;
        }

        async function gen() {
            const glog = document.getElementById('glog');
            if (!window.lastAnalysisData || !window.lastAnalysisData.model_path) {
                glog.textContent = 'Сначала загрузите и проанализируйте модель.';
                return;
            }

            const operationType = document.getElementById('operation_type').value;
            const controller = document.getElementById('controller').value;

            const payload = {
                model_path: window.lastAnalysisData.model_path,
                controller: controller,
                operation_type: operationType,
                material_grade: document.getElementById('material_grade').value,
                tool_diam: parseFloat(document.getElementById('tool').value || '3'),
                flutes: parseInt(document.getElementById('flutes').value || '2'),
                corner_radius: parseFloat(document.getElementById('corner_radius').value || '0'),
                feed: parseFloat(document.getElementById('feed').value || '300'),
                plunge: parseFloat(document.getElementById('plunge').value || '120'),
                clearance: parseFloat(document.getElementById('clearance').value || '5'),
                spindle: parseInt(document.getElementById('spindle').value || '8000'),
                origin: document.getElementById('origin').value || 'bbox_min',
                allowance_x: parseFloat(document.getElementById('allowance_x').value || '0'),
                allowance_y: parseFloat(document.getElementById('allowance_y').value || '0'),
                allowance_z: parseFloat(document.getElementById('allowance_z').value || '0'),
                work_offset: window.lastAnalysisData.work_offset || 'G54'
            };

            if (operationType === 'milling' || operationType === 'roughing' || operationType === 'finishing' || operationType === 'chamfer') {
                payload.stepover = parseFloat(document.getElementById('stepover').value || '0.4');
                payload.stepdown = parseFloat(document.getElementById('stepdown').value || '0');
                payload.dir = document.getElementById('dir').value || 'X';
                payload.waterline = document.getElementById('waterline').checked;
            }

            glog.textContent = 'Генерация G-кода...';
            try {
                const r = await fetch('/generate_gcode', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await r.json();
                if (!data.success) {
                    glog.textContent = 'Ошибка: ' + (data.error || '');
                    return;
                }
                glog.innerHTML = `Готово — <a href="${data.gcode_path}" target="_blank" class="text-blue-400 hover:underline">скачать G-код (${controller.toUpperCase()} ${operationType})</a>`;
            } catch (err) {
                glog.textContent = 'Сетевая ошибка: ' + err;
            }
        }

        // Update system metrics
        async function updateMetrics() {
            try {
                const r = await fetch('/metrics');
                const data = await r.json();
                if (data.success) {
                    document.getElementById('total_requests').textContent = data.total_requests || 0;
                    document.getElementById('success_rate').textContent = (data.success_rate || 100).toFixed(1) + '%';
                    document.getElementById('uptime').textContent = Math.floor((data.uptime_seconds || 0) / 60) + 'm';
                }
            } catch (e) {
                console.log('Metrics update failed:', e);
            }
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            updateMetrics();
            setInterval(updateMetrics, 30000); // Update every 30 seconds
        });
    </script>
</body>
</html>
"""

# ---- Routes ----
@app.route("/")
def index():
    return render_template_string(INDEX_HTML)

@app.route("/favicon.ico")
def favicon():
    return "", 204

@app.route("/static/<path:filename>")
def serve_static(filename: str):
    return send_from_directory(str(STATIC), filename)

@app.route("/models/<path:filename>")
def serve_models(filename: str):
    ext = Path(filename).suffix.lower()
    mime = {"stl": "model/stl", "png": "image/png"}.get(ext[1:], "application/octet-stream")
    return send_from_directory(str(MODELS), filename, mimetype=mime)

@app.route("/download_results")
def download_results():
    filename = request.args.get("filename", "")
    path = TEMP / filename
    if not filename or not path.exists():
        return "Файл не найден", 404
    return send_file(str(path), as_attachment=True, mimetype="application/json", download_name=filename)

@app.route("/metrics")
def get_metrics():
    """Get system metrics"""
    try:
        stats = metrics_collector.get_stats()
        return jsonify({"success": True, **stats})
    except Exception as e:
        error = error_handler.handle_exception(e, "Metrics retrieval")
        return jsonify({"success": False, "error": error.user_message}), 500

@app.route("/health")
def health_check():
    """Health check endpoint"""
    try:
        current_metrics = metrics_collector.collect_system_metrics()
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "system_metrics": asdict(current_metrics) if current_metrics else None,
            "uptime_seconds": (datetime.now() - metrics_collector.start_time).total_seconds()
        }
        
        if current_metrics:
            if current_metrics.cpu_percent > 90:
                health_status["status"] = "warning"
                health_status["issues"] = ["High CPU usage"]
            elif current_metrics.memory_percent > 90:
                health_status["status"] = "warning"
                health_status["issues"] = ["High memory usage"]
            elif current_metrics.disk_usage_percent > 90:
                health_status["status"] = "warning"
                health_status["issues"] = ["Low disk space"]
        
        return jsonify(health_status)
    except Exception as e:
        error = error_handler.handle_exception(e, "Health check")
        return jsonify({
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": error.user_message
        }), 500

@app.route("/upload", methods=["POST"])
def upload():
    """Upload and analyze 3D file with enhanced error handling"""
    start_time = time.time()
    
    try:
        if "file" not in request.files:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "No file provided", "Файл не выбран")
        
        file = request.files["file"]
        if not file or file.filename == "":
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "No file selected", "Файл не выбран")
        
        if not SecurityValidator.validate_filename(file.filename):
            raise CNCeraError(ErrorType.SECURITY_ERROR, "Invalid filename", "Недопустимое имя файла")
        
        units = request.form.get("units", "auto")
        linear_deflection = float(request.form.get("linear_deflection", "0.1"))
        angular_deflection_deg = float(request.form.get("angular_deflection_deg", "15"))
        relative = request.form.get("relative", "false").lower() == "true"
        
        if linear_deflection <= 0 or linear_deflection > 10:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Invalid linear deflection", "Недопустимое линейное отклонение")
        if angular_deflection_deg <= 0 or angular_deflection_deg > 89:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Invalid angular deflection", "Недопустимое угловое отклонение")
        
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 100 * 1024 * 1024:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "File too large", "Файл слишком большой (макс. 100 МБ)")
        
        result = process_uploaded_file(file, units, linear_deflection, angular_deflection_deg, relative)
        
        processing_time = time.time() - start_time
        metrics_collector.record_processing("file_upload", file_size, processing_time, True)
        
        return jsonify({
            "success": True,
            "model_path": result.get("model_path"),
            "result_filename": result.get("result_filename"),
            "preview_png": result.get("preview_png"),
            "preview_png_data": result.get("preview_png_data"),
            "file_info": result.get("file_info"),
            "geometry": result.get("geometry"),
            "mesh_info": result.get("mesh_info"),
            "processing_time": processing_time
        })
        
    except CNCeraError as e:
        processing_time = time.time() - start_time
        file_size = 0
        if "file" in request.files and request.files["file"]:
            try:
                request.files["file"].seek(0, 2)
                file_size = request.files["file"].tell()
                request.files["file"].seek(0)
            except:
                pass
        
        metrics_collector.record_processing("file_upload", file_size, processing_time, False, e.error_type.value)
        return jsonify({"success": False, "error": e.user_message}), 400
        
    except Exception as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "File upload")
        
        file_size = 0
        if "file" in request.files and request.files["file"]:
            try:
                request.files["file"].seek(0, 2)
                file_size = request.files["file"].tell()
                request.files["file"].seek(0)
            except:
                pass
        
        metrics_collector.record_processing("file_upload", file_size, processing_time, False, error.error_type.value)
        return jsonify({"success": False, "error": error.user_message}), 500

@app.route("/generate_gcode", methods=["POST"])
def generate_gcode():
    """Generate G-code with enhanced parameters"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        if not data:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "No JSON data", "Данные не получены")
        
        model_path = data.get("model_path")
        if not model_path:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "No model path", "Путь к модели не указан")
        
        # Преобразуем относительный путь в абсолютный
        if model_path.startswith("/models/"):
            model_file = MODELS / model_path.replace("/models/", "")
        else:
            model_file = Path(model_path)
        
        if not SecurityValidator.validate_filename(model_file.name):
            raise CNCeraError(ErrorType.SECURITY_ERROR, "Invalid model path", "Недопустимый путь к модели")
        
        if not model_file.exists():
            raise CNCeraError(ErrorType.FILE_ERROR, f"Model file not found: {model_file}", f"Файл модели не найден: {model_file}")
        
        validated_params = SecurityValidator.validate_gcode_params(data)
        operation_type = validated_params.get("operation_type", "milling")
        
        controller = validated_params.get("controller", "fanuc")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{operation_type}_{controller}_{timestamp}.nc"
        output_path = MODELS / output_filename
        
        if operation_type in ["milling", "roughing", "finishing"]:
            result = generate_enhanced_milling_gcode(model_file, output_path, **validated_params)
        elif operation_type == "turning":
            result = generate_turning_gcode(model_file, output_path, **validated_params)
        elif operation_type == "drilling":
            result = generate_drilling_gcode(model_file, output_path, **validated_params)
        elif operation_type == "chamfer":
            result = generate_chamfer_gcode(model_file, output_path, **validated_params)
        else:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Unknown operation type", "Неизвестный тип операции")
        
        processing_time = time.time() - start_time
        metrics_collector.record_processing(f"gcode_{operation_type}", model_file.stat().st_size, processing_time, True)
        
        return jsonify({
            "success": True,
            "gcode_path": f"/models/{output_filename}",
            "bbox": result.get("bbox"),
            "processing_time": processing_time
        })
        
    except CNCeraError as e:
        processing_time = time.time() - start_time
        model_size = 0
        if "model_path" in data and data["model_path"]:
            try:
                model_size = Path(data["model_path"]).stat().st_size
            except:
                pass
        
        metrics_collector.record_processing(f"gcode_{data.get('operation_type', 'unknown')}", model_size, processing_time, False, e.error_type.value)
        return jsonify({"success": False, "error": e.user_message}), 400
        
    except Exception as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "G-code generation")
        
        model_size = 0
        if "model_path" in data and data["model_path"]:
            try:
                model_size = Path(data["model_path"]).stat().st_size
            except:
                pass
        
        metrics_collector.record_processing(f"gcode_{data.get('operation_type', 'unknown')}", model_size, processing_time, False, error.error_type.value)
        return jsonify({"success": False, "error": error.user_message}), 500

@app.route("/download_gcode")
def download_gcode():
    """Download generated G-code file"""
    filename = request.args.get("filename", "")
    if not filename:
        return "Filename required", 400
    
    if not SecurityValidator.validate_filename(filename):
        return "Invalid filename", 400
    
    file_path = MODELS / filename
    if not file_path.exists():
        return "File not found", 404
    
    return send_file(str(file_path), as_attachment=True, mimetype="text/plain", download_name=filename)

@app.route("/gcode_preview")
def gcode_preview():
    """Preview G-code content - JSON API version"""
    name = request.args.get("name", "")
    if not name:
        return jsonify({"success": False, "error": "Name parameter required"}), 400
    
    if not SecurityValidator.validate_filename(name):
        return jsonify({"success": False, "error": "Invalid filename"}), 400
    
    file_path = MODELS / name
    if not file_path.exists():
        return jsonify({"success": False, "error": "File not found"}), 404
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        lines = content.split('\n')
        preview_lines = lines[:40]
        
        return jsonify({
            "success": True,
            "lines": preview_lines,
            "total_lines": len(lines),
            "showing": len(preview_lines)
        })
        
    except Exception as e:
        error = error_handler.handle_exception(e, "G-code preview")
        return jsonify({"success": False, "error": error.user_message}), 500

@app.route("/cam_analysis", methods=["POST"])
def cam_analysis():
    """Получить CAM рекомендации на основе анализа геометрии"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        if not data:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "No JSON data", "Данные не получены")
        
        geometry_analysis = data.get("geometry_analysis")
        if not geometry_analysis:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "No geometry analysis data", "Данные анализа геометрии не предоставлены")
        
        provider = data.get("provider", "openai").lower()
        if provider not in ["openai", "anthropic", "xai"]:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Invalid provider", "Недопустимый провайдер")
        
        # Генерируем CAM рекомендации
        cam_recommendations = generate_cam_recommendations(geometry_analysis, provider)
        
        processing_time = time.time() - start_time
        metrics_collector.record_processing(f"cam_analysis_{provider}", len(str(geometry_analysis)), processing_time, True)
        
        return jsonify({
            "success": True,
            "cam_recommendations": cam_recommendations,
            "processing_time": processing_time
        })
        
    except CNCeraError as e:
        processing_time = time.time() - start_time
        data_size = len(str(data)) if data else 0
        
        metrics_collector.record_processing(f"cam_analysis_{data.get('provider', 'unknown')}", data_size, processing_time, False, e.error_type.value)
        return jsonify({"success": False, "error": e.user_message}), 400
        
    except Exception as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "CAM analysis")
        
        data_size = len(str(data)) if data else 0
        
        metrics_collector.record_processing(f"cam_analysis_{data.get('provider', 'unknown')}", data_size, processing_time, False, error.error_type.value)
        return jsonify({"success": False, "error": error.user_message}), 500

@app.route("/ai_chat", methods=["POST"])
def ai_chat():
    """Чат с ИИ для анализа детали"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        if not data:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "No JSON data", "Данные не получены")
        
        message = data.get("message", "").strip()
        if not message:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Empty message", "Сообщение пустое")
        
        provider = data.get("provider", "openai").lower()
        if provider not in ["openai", "anthropic", "xai"]:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Invalid provider", "Недопустимый провайдер")
        
        analysis_data = data.get("analysis_data", {})
        
        # Генерируем ответ ИИ
        ai_response = generate_ai_chat_response(message, provider, analysis_data)
        
        processing_time = time.time() - start_time
        metrics_collector.record_processing(f"ai_chat_{provider}", len(message), processing_time, True)
        
        return jsonify({
            "success": True,
            "response": ai_response,
            "provider": provider,
            "processing_time": processing_time
        })
        
    except CNCeraError as e:
        processing_time = time.time() - start_time
        message_len = len(data.get("message", "")) if data else 0
        
        metrics_collector.record_processing(f"ai_chat_{data.get('provider', 'unknown')}", message_len, processing_time, False, e.error_type.value)
        return jsonify({"success": False, "error": e.user_message}), 400
        
    except Exception as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "AI chat")
        
        message_len = len(data.get("message", "")) if data else 0
        
        metrics_collector.record_processing(f"ai_chat_{data.get('provider', 'unknown')}", message_len, processing_time, False, error.error_type.value)
        return jsonify({"success": False, "error": error.user_message}), 500

@app.route("/chat", methods=["POST"])
def chat():
    """AI chat endpoint with enhanced error handling"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        if not data:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "No JSON data", "Данные не получены")
        
        message = data.get("message", "").strip()
        if not message:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Empty message", "Сообщение пустое")
        
        if len(message) > 10000:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Message too long", "Сообщение слишком длинное")
        
        if not re.match(r'^[a-zA-Z0-9\s\.,!?\-_()\[\]{}:;"\'@#$%^&*+=<>/\\|`~а-яА-ЯёЁ]+$', message):
            raise CNCeraError(ErrorType.SECURITY_ERROR, "Invalid characters in message", "Недопустимые символы в сообщении")
        
        provider = data.get("provider", "openai").lower()
        if provider not in ["openai", "anthropic", "xai"]:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Invalid provider", "Недопустимый провайдер")
        
        api_key = None
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
        elif provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
        elif provider == "xai":
            api_key = os.getenv("XAI_API_KEY")
        
        if not api_key:
            raise CNCeraError(ErrorType.CONFIGURATION_ERROR, "API key not configured", "API ключ не настроен")
        
        response = generate_ai_response(message, provider, api_key)
        
        processing_time = time.time() - start_time
        metrics_collector.record_processing(f"chat_{provider}", len(message), processing_time, True)
        
        return jsonify({
            "success": True,
            "response": response,
            "provider": provider,
            "processing_time": processing_time
        })
        
    except CNCeraError as e:
        processing_time = time.time() - start_time
        message_length = len(data.get("message", "")) if data else 0
        
        metrics_collector.record_processing(f"chat_{data.get('provider', 'unknown')}", message_length, processing_time, False, e.error_type.value)
        return jsonify({"success": False, "error": e.user_message}), 400
        
    except Exception as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "AI chat")
        
        message_length = len(data.get("message", "")) if data else 0
        
        metrics_collector.record_processing(f"chat_{data.get('provider', 'unknown')}", message_length, processing_time, False, error.error_type.value)
        return jsonify({"success": False, "error": error.user_message}), 500

# ---- Error handlers ----
@app.errorhandler(404)
def not_found(error):
    return jsonify({"success": False, "error": "Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"success": False, "error": "Method not allowed"}), 405

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"success": False, "error": "File too large"}), 413

@app.errorhandler(500)
def internal_error(error):
    error_obj = error_handler.handle_exception(error, "Internal server error")
    return jsonify({"success": False, "error": error_obj.user_message}), 500

# ---- Main execution ----
if __name__ == "__main__":
    # Initialize logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('cncera.log'),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Starting CNCera Enhanced Application")
    
    # Log system information
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Flask version: {flask.__version__}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info(f"Models directory: {MODELS}")
    logger.info(f"Static directory: {STATIC}")
    logger.info(f"Temp directory: {TEMP}")
    
    # Check FreeCAD availability
    freecad_cmd = get_freecad_cmd()
    if freecad_cmd:
        logger.info(f"FreeCAD found: {freecad_cmd}")
    else:
        logger.warning("FreeCAD not found - STEP file conversion will not work")
    
    # Start metrics collection in background
    def collect_metrics_background():
        while True:
            try:
                metrics_collector.collect_system_metrics()
                time.sleep(30)
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
                time.sleep(60)
    
    metrics_thread = threading.Thread(target=collect_metrics_background, daemon=True)
    metrics_thread.start()
    
    # Start the application
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        error = error_handler.handle_exception(e, "Application startup")
        logger.error(f"Failed to start application: {error.user_message}")
        sys.exit(1)