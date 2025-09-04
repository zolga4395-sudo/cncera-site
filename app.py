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
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from flask import Flask, request, jsonify, send_from_directory, send_file, render_template_string
from werkzeug.utils import secure_filename
import openai
from datetime import datetime
import re

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

# ---- AI Configuration ----
# Set your OpenAI API key here or via environment variable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# ---- Chat history storage ----
chat_sessions = {}

# ---- Global error handler ----
@app.errorhandler(Exception)
def handle_error(e):
    logger.error("Uncaught exception: %s", e, exc_info=True)
    if request.path in ("/upload", "/generate_gcode", "/ai_chat", "/ai_analyze"):
        return jsonify({"success": False, "error": f"Critical error: {e.__class__.__name__}: {str(e)}"}), 200
    return "Internal Server Error", 500

# ---- AI Helper Functions ----
def analyze_part_with_ai(stl_path: Path, part_info: Dict) -> Dict:
    """Analyze a part using AI to suggest machining strategies"""
    if not OPENAI_API_KEY:
        return {"error": "OpenAI API key not configured"}
    
    try:
        # Extract key information about the part
        dimensions = part_info.get("geometry", {}).get("dimensions", {})
        mesh_info = part_info.get("mesh_info", {})
        
        analysis_prompt = f"""
        Analyze this 3D part for CNC machining:
        
        Dimensions: {dimensions.get('length', 0):.1f} x {dimensions.get('width', 0):.1f} x {dimensions.get('height', 0):.1f} mm
        Mesh complexity: {mesh_info.get('vertices', 0)} vertices, {mesh_info.get('faces', 0)} faces
        
        Please provide:
        1. Recommended machining strategy (roughing, finishing, etc.)
        2. Suggested tool sizes and types
        3. Optimal cutting parameters (feeds, speeds)
        4. Workholding recommendations
        5. Potential challenges and solutions
        6. Estimated machining time
        
        Format the response as structured JSON with these sections.
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert CNC machining engineer. Provide detailed technical analysis."},
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
        logger.error(f"AI analysis failed: {e}")
        return {"error": f"AI analysis failed: {str(e)}"}

def generate_gcode_with_ai(stl_path: Path, part_info: Dict, requirements: str) -> Dict:
    """Generate G-code parameters using AI analysis"""
    if not OPENAI_API_KEY:
        return {"error": "OpenAI API key not configured"}
    
    try:
        dimensions = part_info.get("geometry", {}).get("dimensions", {})
        
        gcode_prompt = f"""
        Generate optimal CNC parameters for this part:
        
        Part dimensions: {dimensions.get('length', 0):.1f} x {dimensions.get('width', 0):.1f} x {dimensions.get('height', 0):.1f} mm
        Requirements: {requirements}
        
        Provide JSON with these parameters:
        {{
            "tool_diameter": <mm>,
            "spindle_speed": <rpm>,
            "feed_rate": <mm/min>,
            "plunge_rate": <mm/min>,
            "stepover": <0.1-0.8>,
            "stepdown": <mm>,
            "operation_type": "milling|roughing|finishing",
            "controller": "fanuc|siemens|heidenhain",
            "strategy": "description of machining strategy",
            "estimated_time": "time estimate"
        }}
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a CNC programming expert. Generate optimal machining parameters."},
                {"role": "user", "content": gcode_prompt}
            ],
            max_tokens=800,
            temperature=0.2
        )
        
        ai_params = response.choices[0].message.content
        
        # Try to parse as JSON
        try:
            return json.loads(ai_params)
        except:
            # Extract parameters using regex if JSON parsing fails
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
        logger.error(f"AI G-code generation failed: {e}")
        return {"error": f"AI G-code generation failed: {str(e)}"}

def chat_with_ai(message: str, session_id: str, context: Dict = None) -> str:
    """Chat with AI about CNC machining topics"""
    if not OPENAI_API_KEY:
        return "OpenAI API key not configured. Please set OPENAI_API_KEY environment variable."
    
    try:
        # Initialize session if not exists
        if session_id not in chat_sessions:
            chat_sessions[session_id] = []
        
        # Add context if provided
        context_info = ""
        if context:
            dimensions = context.get("geometry", {}).get("dimensions", {})
            if dimensions:
                context_info = f"\nCurrent part: {dimensions.get('length', 0):.1f} x {dimensions.get('width', 0):.1f} x {dimensions.get('height', 0):.1f} mm"
        
        # Build conversation history
        messages = [
            {"role": "system", "content": f"You are an expert CNC machining assistant. Help with technical questions about CNC programming, tooling, and manufacturing.{context_info}"}
        ]
        
        # Add recent chat history (last 10 messages)
        for msg in chat_sessions[session_id][-10:]:
            messages.append(msg)
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        
        # Store in session history
        chat_sessions[session_id].append({"role": "user", "content": message})
        chat_sessions[session_id].append({"role": "assistant", "content": ai_response})
        
        # Keep only last 20 messages to avoid token limits
        if len(chat_sessions[session_id]) > 20:
            chat_sessions[session_id] = chat_sessions[session_id][-20:]
        
        return ai_response
        
    except Exception as e:
        logger.error(f"AI chat failed: {e}")
        return f"Sorry, I encountered an error: {str(e)}"

# ---- Utility functions ----
def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

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

# ---- STL mesh analysis ----
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

# ---- PNG rendering for STL ----
def render_stl_to_png(stl_path: Path, png_path: Path) -> bool:
    if matplotlib is None or stlmesh is None:
        logger.warning("matplotlib or numpy-stl not available: PNG preview disabled")
        return False

# Import additional functions
from gcode_functions import *

# ---- Locate FreeCADCmd ----
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

# ---- STEP to STL conversion ----
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

# Import additional functions
from gcode_functions import *

# ---- Locate FreeCADCmd ----
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

# ---- STEP to STL conversion ----
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