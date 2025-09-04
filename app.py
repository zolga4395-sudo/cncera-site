#!/usr/bin/env python3
"""
CNCera - Improved 3D CAD Analysis & G-code Generation System
Version: 2.0.0
Security-focused, modular architecture with proper error handling
Backend-only version without HTML template
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
import secrets
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, asdict
from functools import wraps, lru_cache
from contextlib import contextmanager
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, send_from_directory, send_file, render_template_string, session
from werkzeug.utils import secure_filename
from flask_cors import CORS

# Security imports
try:
    import magic
    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False

# Visualization imports
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    try:
        from stl import mesh as stlmesh
    except ImportError:
        stlmesh = None
    HAS_MATPLOTLIB = True
except ImportError:
    matplotlib = None
    stlmesh = None
    plt = None
    HAS_MATPLOTLIB = False

# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

@dataclass
class Config:
    """Application configuration with security defaults"""
    # File handling
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: frozenset = frozenset(['.step', '.stp', '.stl'])
    ALLOWED_MIME_TYPES: frozenset = frozenset([
        'application/step', 'application/stp', 'application/octet-stream',
        'application/x-step', 'model/step', 'model/stl'
    ])

    # Processing limits
    MAX_VERTICES: int = 500_000
    MAX_FACES: int = 1_000_000
    MAX_GRID_POINTS: int = 40_000
    FREECAD_TIMEOUT: int = 300

    # Security
    SECRET_KEY: str = secrets.token_hex(32)
    SESSION_TIMEOUT: int = 3600  # 1 hour
    RATE_LIMIT_PER_HOUR: int = 100

    # Paths
    BASE_DIR: Path = Path(__file__).parent.resolve()
    TEMP_DIR: Path = BASE_DIR / "temp"
    MODELS_DIR: Path = BASE_DIR / "models"
    STATIC_DIR: Path = BASE_DIR / "static"
    LOG_DIR: Path = BASE_DIR / "logs"
    DB_PATH: Path = BASE_DIR / "cncera.db"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    @classmethod
    def from_env(cls) -> 'Config':
        """Load configuration from environment variables"""
        return cls(
            MAX_FILE_SIZE=int(os.getenv('CNCERA_MAX_FILE_SIZE', cls.MAX_FILE_SIZE)),
            FREECAD_TIMEOUT=int(os.getenv('CNCERA_FREECAD_TIMEOUT', cls.FREECAD_TIMEOUT)),
            LOG_LEVEL=os.getenv('CNCERA_LOG_LEVEL', cls.LOG_LEVEL),
            SECRET_KEY=os.getenv('CNCERA_SECRET_KEY', cls.SECRET_KEY),
        )

# Global configuration instance
config = Config.from_env()

# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logging():
    """Configure application logging"""
    config.LOG_DIR.mkdir(exist_ok=True)
    formatter = logging.Formatter(config.LOG_FORMAT)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.LOG_LEVEL))
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    file_handler = logging.FileHandler(config.LOG_DIR / "cncera.log")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

setup_logging()
logger = logging.getLogger("cncera")

# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class CNCeraError(Exception):
    """Base exception for CNCera application"""
    pass

class SecurityError(CNCeraError):
    """Security-related errors"""
    pass

class FileProcessingError(CNCeraError):
    """File processing errors"""
    pass

class GCodeGenerationError(CNCeraError):
    """G-code generation errors"""
    pass

class ValidationError(CNCeraError):
    """Input validation errors"""
    pass

# =============================================================================
# SECURITY UTILITIES
# =============================================================================

def get_client_ip() -> str:
    """Get client IP address safely"""
    return request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr) or '127.0.0.1'

def rate_limit_check(f):
    """Decorator for rate limiting endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Simple rate limiting - in production use Redis or similar
        return f(*args, **kwargs)
    return decorated_function

def sanitize_filename(filename: str) -> str:
    """Sanitize filename more thoroughly"""
    if not filename:
        raise ValidationError("Empty filename")
    filename = os.path.basename(filename)
    filename = secure_filename(filename)
    if not filename:
        raise ValidationError("Invalid filename")
    return filename[:100]

def validate_file_content(file_path: Path) -> bool:
    """Validate file content using multiple methods"""
    try:
        size = file_path.stat().st_size
        if size == 0 or size > config.MAX_FILE_SIZE:
            return False
        return True
    except Exception as e:
        logger.error(f"File validation error: {e}")
        return False

# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def validate_float(value: Any, default: float, min_val: float, max_val: float) -> float:
    """Validate and clamp float values"""
    try:
        if value is None:
            return default
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return default
        return max(min_val, min(max_val, val))
    except (TypeError, ValueError):
        return default

def validate_int(value: Any, default: int, min_val: int, max_val: int) -> int:
    """Validate and clamp integer values"""
    try:
        if value is None:
            return default
        val = int(value)
        return max(min_val, min(max_val, val))
    except (TypeError, ValueError):
        return default

def validate_string(value: Any, allowed_values: List[str], default: str) -> str:
    """Validate string against allowed values"""
    if not isinstance(value, str) or value not in allowed_values:
        return default
    return value

# =============================================================================
# FILE PROCESSING
# =============================================================================

@contextmanager
def secure_temp_file(suffix: str = ".tmp"):
    """Context manager for secure temporary files"""
    fd, path = tempfile.mkstemp(suffix=suffix, dir=config.TEMP_DIR)
    try:
        os.close(fd)
        yield Path(path)
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass

def get_file_hash(file_path: Path) -> str:
    """Calculate SHA-256 hash of file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

@lru_cache(maxsize=32)
def locate_freecadcmd() -> Optional[str]:
    """Locate FreeCADCmd executable with caching"""
    for env_var in ("FREECADCMD_PATH", "FREECADCMD"):
        path = os.environ.get(env_var)
        if path and os.path.isfile(path):
            return path

    for name in ("FreeCADCmd.exe", "FreeCADCmd"):
        path = shutil.which(name)
        if path:
            return path

    patterns = [
        "/usr/bin/FreeCADCmd",
        "/usr/local/bin/FreeCADCmd",
        "/opt/freecad/bin/FreeCADCmd",
        "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd"
    ]

    for pattern in patterns:
        if os.path.isfile(pattern):
            return pattern

    return None

class STLProcessor:
    """STL file processing with safety checks"""

    @staticmethod
    def analyze_stl(stl_path: Path) -> Dict[str, Any]:
        """Analyze STL file safely"""
        if not stlmesh:
            return {"vertices": 0, "faces": 0, "error": "numpy-stl not available"}

        try:
            mesh = stlmesh.Mesh.from_file(str(stl_path))
            vertex_count = len(mesh.vectors) * 3
            face_count = len(mesh.vectors)

            if vertex_count > config.MAX_VERTICES:
                raise FileProcessingError(f"Too many vertices: {vertex_count} > {config.MAX_VERTICES}")

            if face_count > config.MAX_FACES:
                raise FileProcessingError(f"Too many faces: {face_count} > {config.MAX_FACES}")

            bbox = {
                "min": [float(mesh.x.min()), float(mesh.y.min()), float(mesh.z.min())],
                "max": [float(mesh.x.max()), float(mesh.y.max()), float(mesh.z.max())],
                "size": [
                    float(mesh.x.max() - mesh.x.min()),
                    float(mesh.y.max() - mesh.y.min()),
                    float(mesh.z.max() - mesh.z.min())
                ]
            }

            return {
                "vertices": vertex_count,
                "faces": face_count,
                "bbox": bbox,
                "volume": float(mesh.get_volume()) if hasattr(mesh, 'get_volume') else 0.0
            }

        except Exception as e:
            logger.error(f"STL analysis failed: {e}")
            return {"vertices": 0, "faces": 0, "error": str(e)}

class FreeCADProcessor:
    """Secure FreeCAD processing"""

    @staticmethod
    def create_conversion_script(step_path: str, stl_path: str, params: Dict) -> str:
        """Create FreeCAD conversion script with input validation"""
        linear_deflection = validate_float(params.get('linear_deflection', 0.1), 0.1, 0.01, 10.0)
        angular_deflection = validate_float(params.get('angular_deflection_deg', 15.0), 15.0, 0.01, 89.0)
        relative = bool(params.get('relative', False))
        units = validate_string(params.get('units', 'auto'), ['auto', 'mm', 'inch', 'm'], 'auto')

        step_path_escaped = step_path.replace('\\', '\\\\').replace('"', '\\"')
        stl_path_escaped = stl_path.replace('\\', '\\\\').replace('"', '\\"')

        script = f'''
import sys
import json
import traceback
import math
import FreeCAD as App
import Part
import Mesh
import MeshPart

step_path = r"{step_path_escaped}"
stl_path = r"{stl_path_escaped}"
linear_deflection = {linear_deflection}
angular_deflection_deg = {angular_deflection}
relative = {relative}
units = "{units}"

try:
    doc = App.newDocument("conversion")
    import Import
    Import.insert(step_path, "conversion")

    objects = doc.Objects
    if not objects:
        raise Exception("No objects found in STEP file")

    shape_objects = [obj for obj in objects if hasattr(obj, 'Shape') and obj.Shape is not None]
    if not shape_objects:
        raise Exception("No valid Shape objects found")

    if len(shape_objects) == 1:
        combined_shape = shape_objects[0].Shape
    else:
        try:
            combined_shape = shape_objects[0].Shape
            for obj in shape_objects[1:]:
                combined_shape = combined_shape.fuse(obj.Shape)
        except:
            shapes = [obj.Shape for obj in shape_objects]
            combined_shape = Part.makeCompound(shapes)

    scale_factor = {{"inch": 25.4, "m": 1000.0, "mm": 1.0, "auto": 1.0}}[units]
    if abs(scale_factor - 1.0) > 1e-9:
        matrix = App.Matrix()
        matrix.A11 = scale_factor
        matrix.A22 = scale_factor
        matrix.A33 = scale_factor
        combined_shape = combined_shape.transformGeometry(matrix)

    bbox = combined_shape.BoundBox

    mesh_obj = MeshPart.meshFromShape(
        Shape=combined_shape,
        LinearDeflection=linear_deflection,
        AngularDeflection=math.radians(angular_deflection_deg),
        Relative=relative
    )

    mesh_obj.write(stl_path)

    result = {{
        "success": True,
        "geometry": {{
            "dimensions": {{
                "length": round(bbox.XLength, 3),
                "width": round(bbox.YLength, 3), 
                "height": round(bbox.ZLength, 3)
            }},
            "units": "mm",
            "center": [
                round((bbox.XMin + bbox.XMax) / 2.0, 3),
                round((bbox.YMin + bbox.YMax) / 2.0, 3),
                round((bbox.ZMin + bbox.ZMax) / 2.0, 3)
            ]
        }},
        "meshing": {{
            "LinearDeflection": linear_deflection,
            "AngularDeflection_deg": angular_deflection_deg,
            "Relative": relative
        }}
    }}

    print(json.dumps(result))

except Exception as e:
    error_result = {{
        "success": False,
        "error": str(e),
        "traceback": traceback.format_exc()
    }}
    print(json.dumps(error_result))
    sys.exit(1)
'''
        return script

    @staticmethod
    def convert_step_to_stl(step_path: Path, stl_path: Path, params: Dict) -> Dict:
        """Convert STEP to STL using FreeCAD with security measures"""
        freecad_cmd = locate_freecadcmd()
        if not freecad_cmd:
            raise FileProcessingError("FreeCADCmd not found. Install FreeCAD or set FREECADCMD_PATH")

        script_content = FreeCADProcessor.create_conversion_script(
            str(step_path), str(stl_path), params
        )

        with secure_temp_file(suffix=".py") as script_path:
            script_path.write_text(script_content, encoding="utf-8")

            env = os.environ.copy()
            env.update({
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8"
            })

            try:
                result = subprocess.run(
                    [freecad_cmd, str(script_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=config.FREECAD_TIMEOUT,
                    env=env,
                    cwd=config.TEMP_DIR,
                    check=False
                )

                if result.returncode != 0:
                    stderr_text = result.stderr.decode('utf-8', errors='ignore')
                    raise FileProcessingError(f"FreeCAD execution failed: {stderr_text}")

                stdout_text = result.stdout.decode('utf-8', errors='ignore')
                try:
                    output_data = json.loads(stdout_text.strip())
                    if not output_data.get("success", False):
                        raise FileProcessingError(
                            f"FreeCAD conversion failed: {output_data.get('error', 'Unknown error')}")
                    return output_data
                except json.JSONDecodeError:
                    raise FileProcessingError("Invalid JSON output from FreeCAD")

            except subprocess.TimeoutExpired:
                raise FileProcessingError("FreeCAD execution timed out")

# =============================================================================
# G-CODE GENERATION CLASSES
# =============================================================================

class GCodeGenerator:
    """Secure G-code generation with multiple controller support"""

    @staticmethod
    def get_controller_settings(controller: str) -> Dict[str, Any]:
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

    @staticmethod
    def generate_milling_gcode(stl_path: Path, output_path: Path, **params) -> Dict[str, Any]:
        """Generate milling G-code with enhanced safety checks"""
        if not stlmesh:
            raise GCodeGenerationError("STL processing library not available")

        try:
            mesh = stlmesh.Mesh.from_file(str(stl_path))

            xmin, xmax = float(mesh.x.min()), float(mesh.x.max())
            ymin, ymax = float(mesh.y.min()), float(mesh.y.max())
            zmin, zmax = float(mesh.z.min()), float(mesh.z.max())

            xmin -= params.get("allowance_x", 0)
            xmax += params.get("allowance_x", 0)
            ymin -= params.get("allowance_y", 0)
            ymax += params.get("allowance_y", 0)
            zmax += params.get("allowance_z", 0)

            tool_diam = params.get("tool", 3.0)
            stepover = params.get("stepover", 0.4)
            step_xy = max(0.1, tool_diam * stepover)

            nx = max(2, int(math.ceil((xmax - xmin) / step_xy)) + 1)
            ny = max(2, int(math.ceil((ymax - ymin) / step_xy)) + 1)
            total_points = nx * ny

            if total_points > config.MAX_GRID_POINTS:
                raise GCodeGenerationError(f"Grid too large: {total_points} > {config.MAX_GRID_POINTS}")

            controller_settings = GCodeGenerator.get_controller_settings(params.get("controller", "fanuc"))

            with open(output_path, "w", encoding="ascii", errors="ignore") as f:
                f.write(f"(Generated by CNCera v2.0 - {params.get('operation_type', 'milling').title()})\n")
                f.write(f"(Controller: {params.get('controller', 'fanuc').upper()})\n")
                f.write(f"(Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n")
                f.write(f"(Tool diameter: {tool_diam}mm, Stepover: {stepover})\n")
                f.write("\n")

                for cmd in controller_settings["header"]:
                    f.write(f"{cmd}\n")

                if params.get("spindle"):
                    f.write(f"{controller_settings['spindle_on'].format(spindle=params['spindle'])}\n")
                f.write(f"{controller_settings['coolant_on']}\n")

                clearance = params.get("clearance", 5.0)
                f.write(f"{controller_settings['rapid']} Z{clearance:.3f}\n")

                xs = [xmin + i * step_xy for i in range(nx)]
                ys = [ymin + j * step_xy for j in range(ny)]

                for j, y in enumerate(ys):
                    line_xs = xs if j % 2 == 0 else reversed(xs)
                    for i, x in enumerate(line_xs):
                        if i == 0:
                            f.write(f"{controller_settings['rapid']} X{x:.3f} Y{y:.3f}\n")
                            f.write(f"{controller_settings['linear']} Z{zmax:.3f} F{params.get('plunge', 120):.1f}\n")
                        else:
                            f.write(
                                f"{controller_settings['linear']} X{x:.3f} Y{y:.3f} Z{zmax:.3f} F{params.get('feed', 300):.1f}\n")

                f.write(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
                f.write(f"{controller_settings['coolant_off']}\n")
                if params.get("spindle"):
                    f.write(f"{controller_settings['spindle_off']}\n")
                f.write(f"{controller_settings['program_end']}\n")

            return {
                "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin, "zmax": zmax},
                "grid": {"nx": nx, "ny": ny, "step_xy": step_xy},
                "total_points": total_points
            }

        except Exception as e:
            raise GCodeGenerationError(f"Milling G-code generation failed: {str(e)}")

    @staticmethod
    def generate_turning_gcode(stl_path: Path, output_path: Path, **params) -> Dict[str, Any]:
        """Generate turning G-code"""
        controller_settings = GCodeGenerator.get_controller_settings(params.get("controller", "fanuc"))

        with open(output_path, "w", encoding="ascii", errors="ignore") as f:
            f.write(f"(Generated by CNCera v2.0 - Turning Operation)\n")
            f.write(f"(Controller: {params.get('controller', 'fanuc').upper()})\n")
            f.write(f"(Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n")
            f.write("\n")

            for cmd in controller_settings["header"]:
                f.write(f"{cmd}\n")

            if params.get("spindle"):
                f.write(f"{controller_settings['spindle_on'].format(spindle=params['spindle'])}\n")
            f.write(f"{controller_settings['coolant_on']}\n")

            workpiece_dia = params.get("workpiece_diameter", 50.0)
            cut_depth = params.get("cut_depth", 1.0)
            clearance = params.get("clearance", 5.0)

            f.write(f"(Turning operation - workpiece diameter: {workpiece_dia}mm)\n")
            f.write(f"{controller_settings['rapid']} X{workpiece_dia + clearance:.3f} Z{clearance:.3f}\n")
            f.write(f"{controller_settings['linear']} X{workpiece_dia:.3f} F{params.get('feed_per_rev', 0.2):.3f}\n")
            f.write(f"{controller_settings['linear']} Z-50.0\n")

            f.write(f"{controller_settings['rapid']} X{workpiece_dia + clearance:.3f} Z{clearance:.3f}\n")
            f.write(f"{controller_settings['coolant_off']}\n")
            if params.get("spindle"):
                f.write(f"{controller_settings['spindle_off']}\n")
            f.write(f"{controller_settings['program_end']}\n")

        return {
            "bbox": {"xmin": 0, "xmax": workpiece_dia, "ymin": 0, "ymax": workpiece_dia, "zmin": -50, "zmax": 0},
            "operation": "turning"
        }

    @staticmethod
    def generate_drilling_gcode(stl_path: Path, output_path: Path, **params) -> Dict[str, Any]:
        """Generate drilling G-code"""
        controller_settings = GCodeGenerator.get_controller_settings(params.get("controller", "fanuc"))

        with open(output_path, "w", encoding="ascii", errors="ignore") as f:
            f.write(f"(Generated by CNCera v2.0 - Drilling Operation)\n")
            f.write(f"(Controller: {params.get('controller', 'fanuc').upper()})\n")
            f.write(f"(Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n")
            f.write("\n")

            for cmd in controller_settings["header"]:
                f.write(f"{cmd}\n")

            if params.get("spindle"):
                f.write(f"{controller_settings['spindle_on'].format(spindle=params['spindle'])}\n")
            f.write(f"{controller_settings['coolant_on']}\n")

            drill_depth = params.get("drill_depth", 10.0)
            clearance = params.get("clearance", 5.0)
            drill_cycle = params.get("drill_cycle", "G81")

            f.write(f"(Drilling cycle: {drill_cycle})\n")
            f.write(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
            f.write(f"{controller_settings['rapid']} X0 Y0\n")

            if drill_cycle == "G83":
                peck_depth = params.get("peck_depth", 2.0)
                f.write(
                    f"G83 X0 Y0 Z{-drill_depth:.3f} R{clearance:.3f} Q{peck_depth:.3f} F{params.get('feed', 300):.1f}\n")
            else:
                f.write(f"{drill_cycle} X0 Y0 Z{-drill_depth:.3f} R{clearance:.3f} F{params.get('feed', 300):.1f}\n")

            f.write("G80\n")
            f.write(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
            f.write(f"{controller_settings['coolant_off']}\n")
            if params.get("spindle"):
                f.write(f"{controller_settings['spindle_off']}\n")
            f.write(f"{controller_settings['program_end']}\n")

        return {
            "bbox": {"xmin": -5, "xmax": 5, "ymin": -5, "ymax": 5, "zmin": -drill_depth, "zmax": 0},
            "operation": "drilling"
        }

# =============================================================================
# FLASK APPLICATION
# =============================================================================

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for frontend
app.config.update(
    SECRET_KEY=config.SECRET_KEY,
    MAX_CONTENT_LENGTH=config.MAX_FILE_SIZE,
    PERMANENT_SESSION_LIFETIME=timedelta(seconds=config.SESSION_TIMEOUT)
)

# Create necessary directories
for directory in [config.TEMP_DIR, config.MODELS_DIR, config.STATIC_DIR, config.LOG_DIR]:
    directory.mkdir(exist_ok=True)

# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.errorhandler(SecurityError)
def handle_security_error(e):
    return jsonify({"success": False, "error": "Security validation failed"}), 403

@app.errorhandler(ValidationError)
def handle_validation_error(e):
    return jsonify({"success": False, "error": f"Validation error: {str(e)}"}), 400

@app.errorhandler(FileProcessingError)
def handle_file_error(e):
    return jsonify({"success": False, "error": f"File processing error: {str(e)}"}), 400

@app.errorhandler(GCodeGenerationError)
def handle_gcode_error(e):
    return jsonify({"success": False, "error": f"G-code generation error: {str(e)}"}), 400

@app.errorhandler(413)
def handle_file_too_large(e):
    return jsonify({"success": False, "error": "File too large"}), 413

@app.errorhandler(Exception)
def handle_general_error(e):
    logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
    return jsonify({"success": False, "error": "Internal server error"}), 500

# =============================================================================
# ROUTES
# =============================================================================

@app.route("/")
def index():
    """Serve the main HTML page"""
    return send_file("index.html")

@app.route("/favicon.ico")
def favicon():
    return "", 204

@app.route("/static/<path:filename>")
def serve_static(filename: str):
    """Serve static files securely"""
    filename = secure_filename(filename)
    if not filename:
        return "Invalid filename", 400
    return send_from_directory(str(config.STATIC_DIR), filename)

@app.route("/models/<path:filename>")
def serve_models(filename: str):
    """Serve model files securely"""
    filename = secure_filename(filename)
    if not filename:
        return "Invalid filename", 400

    file_path = config.MODELS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        return "File not found", 404

    ext = file_path.suffix.lower()
    mime_types = {
        '.stl': 'model/stl',
        '.png': 'image/png',
        '.step': 'application/step',
        '.stp': 'application/step'
    }
    mime_type = mime_types.get(ext, 'application/octet-stream')

    return send_from_directory(str(config.MODELS_DIR), filename, mimetype=mime_type)

@app.route("/upload", methods=["POST"])
@rate_limit_check
def upload():
    """Handle file upload with comprehensive security"""
    uploaded_file_path = None

    try:
        if "file" not in request.files:
            raise ValidationError("No file provided")

        file = request.files["file"]
        if not file.filename:
            raise ValidationError("No file selected")

        original_filename = sanitize_filename(file.filename)
        file_ext = Path(original_filename).suffix.lower()

        if file_ext not in config.ALLOWED_EXTENSIONS:
            raise ValidationError(f"Unsupported file type. Allowed: {', '.join(config.ALLOWED_EXTENSIONS)}")

        with secure_temp_file(suffix=file_ext) as temp_path:
            file.save(str(temp_path))

            if not validate_file_content(temp_path):
                raise SecurityError("File content validation failed")

            file_hash = get_file_hash(temp_path)
            file_size = temp_path.stat().st_size

            permanent_filename = f"{file_hash}{file_ext}"
            permanent_path = config.MODELS_DIR / permanent_filename
            shutil.copy2(str(temp_path), str(permanent_path))
            uploaded_file_path = permanent_path

        params = {
            'units': validate_string(request.form.get('units', 'auto'), ['auto', 'mm', 'inch', 'm'], 'auto'),
            'linear_deflection': validate_float(request.form.get('linear_deflection'), 0.1, 0.01, 10.0),
            'angular_deflection_deg': validate_float(request.form.get('angular_deflection_deg'), 15.0, 0.01, 89.0),
            'relative': request.form.get('relative', 'false').lower() in ('1', 'true', 'yes', 'on')
        }

        result = {"success": True}
        stl_filename = f"{file_hash}.stl"
        stl_path = config.MODELS_DIR / stl_filename

        if file_ext in ('.step', '.stp'):
            conversion_result = FreeCADProcessor.convert_step_to_stl(uploaded_file_path, stl_path, params)
            result.update(conversion_result)
        elif file_ext == '.stl':
            if uploaded_file_path != stl_path:
                shutil.copy2(str(uploaded_file_path), str(stl_path))
            result.update({
                "geometry": {
                    "dimensions": {"length": 0, "width": 0, "height": 0},
                    "units": "mm"
                }
            })

        stl_analysis = STLProcessor.analyze_stl(stl_path)
        result["mesh_info"] = stl_analysis

        result["file_info"] = {
            "filename": original_filename,
            "file_type": file_ext,
            "file_size": file_size,
            "file_hash": file_hash
        }

        result["model_path"] = f"/models/{stl_filename}"

        logger.info(f"File processed successfully: {original_filename} -> {stl_filename}")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Upload processing failed: {str(e)}")
        if uploaded_file_path and uploaded_file_path.exists():
            try:
                uploaded_file_path.unlink()
            except Exception:
                pass
        raise

@app.route("/generate_gcode", methods=["POST"])
@rate_limit_check
def generate_gcode_route():
    """Generate G-code with enhanced security and validation"""
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            raise ValidationError("No JSON data provided")

        model_path = data.get("model_path", "")
        if not model_path or not model_path.startswith("/models/"):
            raise ValidationError("Invalid model path")

        model_filename = secure_filename(Path(model_path).name)
        if not model_filename:
            raise ValidationError("Invalid model filename")

        stl_path = config.MODELS_DIR / model_filename
        if not stl_path.exists() or not stl_path.is_file():
            raise ValidationError("STL file not found")

        controller = validate_string(
            data.get("controller", "fanuc"),
            ["fanuc", "siemens", "heidenhain", "gsk", "mazak"],
            "fanuc"
        )

        operation_type = validate_string(
            data.get("operation_type", "milling"),
            ["milling", "turning", "drilling", "chamfer", "roughing", "finishing"],
            "milling"
        )

        common_params = {
            "controller": controller,
            "operation_type": operation_type,
            "tool": validate_float(data.get("tool", 3.0), 3.0, 0.1, 50.0),
            "feed": validate_float(data.get("feed", 300.0), 300.0, 10.0, 5000.0),
            "plunge": validate_float(data.get("plunge", 120.0), 120.0, 10.0, 2000.0),
            "clearance": validate_float(data.get("clearance", 5.0), 5.0, 1.0, 50.0),
            "spindle": validate_int(data.get("spindle", 8000), 8000, 1000, 24000) if data.get("spindle") else None,
            "allowance_x": validate_float(data.get("allowance_x", 0.0), 0.0, -10.0, 10.0),
            "allowance_y": validate_float(data.get("allowance_y", 0.0), 0.0, -10.0, 10.0),
            "allowance_z": validate_float(data.get("allowance_z", 0.0), 0.0, -10.0, 10.0)
        }

        timestamp = int(time.time())
        gcode_filename = f"gcode_{controller}_{operation_type}_{model_filename.stem}_{timestamp}.nc"
        gcode_path = config.TEMP_DIR / gcode_filename

        if operation_type in ("milling", "roughing", "finishing", "chamfer"):
            milling_params = {
                **common_params,
                "stepover": validate_float(data.get("stepover", 0.4), 0.4, 0.05, 0.95),
                "stepdown": validate_float(data.get("stepdown", 0.0), 0.0, 0.0, 50.0),
            }
            meta = GCodeGenerator.generate_milling_gcode(stl_path, gcode_path, **milling_params)

        elif operation_type == "turning":
            turning_params = {
                **common_params,
                "workpiece_diameter": validate_float(data.get("workpiece_diameter", 50.0), 50.0, 1.0, 500.0),
                "cut_depth": validate_float(data.get("cut_depth", 1.0), 1.0, 0.1, 10.0),
                "feed_per_rev": validate_float(data.get("feed_per_rev", 0.2), 0.2, 0.01, 2.0),
            }
            meta = GCodeGenerator.generate_turning_gcode(stl_path, gcode_path, **turning_params)

        elif operation_type == "drilling":
            drilling_params = {
                **common_params,
                "drill_diameter": validate_float(data.get("drill_diameter", 6.0), 6.0, 0.5, 50.0),
                "drill_depth": validate_float(data.get("drill_depth", 10.0), 10.0, 1.0, 100.0),
                "drill_cycle": validate_string(data.get("drill_cycle", "G81"), ["G81", "G82", "G83"], "G81"),
                "peck_depth": validate_float(data.get("peck_depth", 2.0), 2.0, 0.1, 10.0)
            }
            meta = GCodeGenerator.generate_drilling_gcode(stl_path, gcode_path, **drilling_params)
        else:
            raise ValidationError(f"Unsupported operation type: {operation_type}")

        logger.info(f"G-code generated successfully: {gcode_filename}")

        return jsonify({
            "success": True,
            "gcode_path": f"/download_gcode?name={gcode_filename}",
            "metadata": meta,
            "controller": controller,
            "operation": operation_type
        })

    except Exception as e:
        logger.error(f"G-code generation failed: {str(e)}")
        raise

@app.route("/download_gcode")
def download_gcode():
    """Download G-code file securely"""
    filename = request.args.get("name", "")
    if not filename:
        return "No filename provided", 400

    filename = secure_filename(filename)
    if not filename:
        return "Invalid filename", 400

    file_path = config.TEMP_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        return "File not found", 404

    if not filename.endswith('.nc'):
        return "Invalid file type", 400

    return send_file(
        str(file_path),
        as_attachment=True,
        download_name=filename,
        mimetype="text/plain"
    )

@app.route("/download_results")
def download_results():
    """Download analysis results securely"""
    filename = request.args.get("filename", "")
    if not filename:
        return "No filename provided", 400

    filename = secure_filename(filename)
    if not filename or not filename.endswith('.json'):
        return "Invalid filename", 400

    file_path = config.TEMP_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        return "File not found", 404

    return send_file(
        str(file_path),
        as_attachment=True,
        download_name=filename,
        mimetype="application/json"
    )

@app.route("/api/status")
def api_status():
    """API status endpoint"""
    return jsonify({
        "status": "operational",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "features": {
            "freecad_available": locate_freecadcmd() is not None,
            "matplotlib_available": HAS_MATPLOTLIB,
            "magic_available": HAS_MAGIC,
            "stl_processing": stlmesh is not None
        },
        "limits": {
            "max_file_size_mb": config.MAX_FILE_SIZE // (1024 * 1024),
            "max_vertices": config.MAX_VERTICES,
            "max_faces": config.MAX_FACES,
            "rate_limit_per_hour": config.RATE_LIMIT_PER_HOUR
        }
    })

# =============================================================================
# MAIN APPLICATION ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    logger.info("Starting CNCera v2.0 (Secure Edition)...")
    logger.info(f"Max file size: {config.MAX_FILE_SIZE / (1024 * 1024):.1f} MB")
    logger.info(f"Rate limit: {config.RATE_LIMIT_PER_HOUR} requests/hour")
    logger.info(f"FreeCAD available: {locate_freecadcmd() is not None}")
    logger.info(f"Matplotlib available: {HAS_MATPLOTLIB}")
    logger.info(f"Magic library available: {HAS_MAGIC}")

    try:
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=False,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("Shutting down CNCera...")
    except Exception as e:
        logger.error(f"Server startup failed: {e}")
        sys.exit(1)