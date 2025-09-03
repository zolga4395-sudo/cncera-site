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
import psutil
import threading
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict, deque
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, send_file, render_template_string
from werkzeug.utils import secure_filename

# ---- Enhanced Imports and Classes ----
class MaterialGroup(Enum):
    """Группы материалов по ISO"""
    P = "P"  # Сталь
    M = "M"  # Нержавеющая сталь
    K = "K"  # Чугун
    N = "N"  # Алюминий
    S = "S"  # Титан/никелевые сплавы
    H = "H"  # Закаленная сталь

class ErrorType(Enum):
    """Типы ошибок в системе"""
    FILE_NOT_FOUND = "file_not_found"
    INVALID_FORMAT = "invalid_format"
    PROCESSING_ERROR = "processing_error"
    VALIDATION_ERROR = "validation_error"
    SYSTEM_ERROR = "system_error"
    TIMEOUT_ERROR = "timeout_error"
    PERMISSION_ERROR = "permission_error"

@dataclass
class Material:
    """Характеристики материала"""
    group: MaterialGroup
    grade: str
    hardness: Optional[str] = None
    notes: str = ""

@dataclass
class Tool:
    """Характеристики инструмента"""
    type: str
    diameter: float
    flutes: int
    corner_radius: float = 0.0
    insert_type: str = ""
    coating: str = ""
    holder: str = ""
    stickout: float = 0.0

@dataclass
class CuttingParams:
    """Параметры резания"""
    Vc: float  # Скорость резания, м/мин
    fz: float  # Подача на зуб, мм/зуб
    fn: float  # Подача на оборот, мм/об
    rpm: int   # Обороты шпинделя
    feed: float # Подача, мм/мин
    ap: float  # Глубина резания, мм
    ae: float  # Ширина резания, мм

@dataclass
class CNCeraError:
    """Структурированная ошибка"""
    error_type: ErrorType
    message: str
    details: Optional[Dict[str, Any]] = None
    user_message: Optional[str] = None
    retry_possible: bool = False

# ---- Enhanced Security and Validation ----
class SecurityValidator:
    """Класс для валидации входных данных и обеспечения безопасности"""
    
    @staticmethod
    def validate_filename(filename: str) -> bool:
        """Проверка имени файла на безопасность"""
        if not filename or len(filename) > 255:
            return False
        
        forbidden_chars = r'[<>:"/\\|?*\x00-\x1f]'
        if re.search(forbidden_chars, filename):
            return False
            
        forbidden_names = {
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }
        
        name_without_ext = Path(filename).stem.upper()
        if name_without_ext in forbidden_names:
            return False
            
        return True
    
    @staticmethod
    def validate_gcode_params(params: dict) -> dict:
        """Валидация параметров G-кода"""
        validated = {}
        
        ranges = {
            'tool_diam': (0.1, 50.0),
            'feed': (10.0, 5000.0),
            'spindle': (100, 24000),
            'clearance': (1.0, 50.0),
            'stepover': (0.05, 0.95),
            'stepdown': (0.0, 50.0)
        }
        
        for key, (min_val, max_val) in ranges.items():
            if key in params:
                try:
                    val = float(params[key])
                    validated[key] = max(min_val, min(max_val, val))
                except (ValueError, TypeError):
                    validated[key] = min_val
        
        return validated

# ---- Enhanced Error Handling ----
class ErrorHandler:
    """Централизованная обработка ошибок"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.error_messages = {
            ErrorType.FILE_NOT_FOUND: "Файл не найден",
            ErrorType.INVALID_FORMAT: "Неподдерживаемый формат файла",
            ErrorType.PROCESSING_ERROR: "Ошибка обработки файла",
            ErrorType.VALIDATION_ERROR: "Ошибка валидации параметров",
            ErrorType.SYSTEM_ERROR: "Системная ошибка",
            ErrorType.TIMEOUT_ERROR: "Превышено время ожидания",
            ErrorType.PERMISSION_ERROR: "Ошибка доступа к файлу"
        }
    
    def handle_exception(self, exc: Exception, context: str = "") -> CNCeraError:
        """Обработка исключения с контекстом"""
        error_type = self._classify_exception(exc)
        message = str(exc)
        
        self.logger.error(f"Error in {context}: {message}", exc_info=True)
        
        error = CNCeraError(
            error_type=error_type,
            message=message,
            details={
                "context": context,
                "exception_type": type(exc).__name__,
                "traceback": traceback.format_exc()
            },
            user_message=self._get_user_friendly_message(error_type),
            retry_possible=self._is_retry_possible(error_type)
        )
        
        return error
    
    def _classify_exception(self, exc: Exception) -> ErrorType:
        """Классификация исключения по типу"""
        exc_name = type(exc).__name__
        
        if "FileNotFoundError" in exc_name or "NoSuchFile" in exc_name:
            return ErrorType.FILE_NOT_FOUND
        elif "TimeoutError" in exc_name or "timeout" in str(exc).lower():
            return ErrorType.TIMEOUT_ERROR
        elif "PermissionError" in exc_name or "access" in str(exc).lower():
            return ErrorType.PERMISSION_ERROR
        elif "ValueError" in exc_name or "validation" in str(exc).lower():
            return ErrorType.VALIDATION_ERROR
        elif "OSError" in exc_name or "IOError" in exc_name:
            return ErrorType.SYSTEM_ERROR
        else:
            return ErrorType.PROCESSING_ERROR
    
    def _get_user_friendly_message(self, error_type: ErrorType) -> str:
        """Получение понятного пользователю сообщения"""
        return self.error_messages.get(error_type, "Произошла неизвестная ошибка")
    
    def _is_retry_possible(self, error_type: ErrorType) -> bool:
        """Определение возможности повтора операции"""
        retry_possible = {
            ErrorType.TIMEOUT_ERROR: True,
            ErrorType.SYSTEM_ERROR: True,
            ErrorType.PROCESSING_ERROR: True,
            ErrorType.FILE_NOT_FOUND: False,
            ErrorType.INVALID_FORMAT: False,
            ErrorType.VALIDATION_ERROR: False,
            ErrorType.PERMISSION_ERROR: False
        }
        return retry_possible.get(error_type, False)

# ---- Enhanced Cutting Speed Calculator ----
class CuttingSpeedCalculator:
    """Калькулятор режимов резания"""
    
    MATERIAL_RANGES = {
        MaterialGroup.P: {"Vc": (120, 220), "fz": (0.02, 0.12)},
        MaterialGroup.M: {"Vc": (80, 180), "fz": (0.02, 0.10)},
        MaterialGroup.K: {"Vc": (160, 260), "fz": (0.03, 0.18)},
        MaterialGroup.N: {"Vc": (250, 600), "fz": (0.04, 0.25)},
        MaterialGroup.S: {"Vc": (60, 120), "fz": (0.02, 0.08)},
        MaterialGroup.H: {"Vc": (80, 150), "fz": (0.01, 0.06)}
    }
    
    @classmethod
    def calculate_milling_params(cls, material: Material, tool: Tool, 
                                operation: str = "roughing") -> CuttingParams:
        """Расчет параметров фрезерования"""
        ranges = cls.MATERIAL_RANGES.get(material.group, cls.MATERIAL_RANGES[MaterialGroup.P])
        
        if operation == "roughing":
            Vc = ranges["Vc"][0] + (ranges["Vc"][1] - ranges["Vc"][0]) * 0.7
            fz = ranges["fz"][0] + (ranges["fz"][1] - ranges["fz"][0]) * 0.8
        else:  # finishing
            Vc = ranges["Vc"][0] + (ranges["Vc"][1] - ranges["Vc"][0]) * 0.9
            fz = ranges["fz"][0] + (ranges["fz"][1] - ranges["fz"][0]) * 0.5
        
        rpm = int(1000 * Vc / (math.pi * tool.diameter))
        feed = fz * tool.flutes * rpm
        
        if operation == "roughing":
            ap = tool.diameter * 0.5
            ae = tool.diameter * 0.4
        else:
            ap = tool.diameter * 0.1
            ae = tool.diameter * 0.2
        
        return CuttingParams(
            Vc=Vc, fz=fz, fn=fz * tool.flutes,
            rpm=rpm, feed=feed, ap=ap, ae=ae
        )

# ---- Monitoring System ----
@dataclass
class SystemMetrics:
    """Системные метрики"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    disk_usage_percent: float
    active_connections: int
    processing_tasks: int

@dataclass
class ProcessingMetrics:
    """Метрики обработки"""
    timestamp: datetime
    operation_type: str
    file_size: int
    processing_time: float
    success: bool
    error_type: Optional[str] = None

class MetricsCollector:
    """Сборщик метрик"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.system_metrics = deque(maxlen=max_history)
        self.processing_metrics = deque(maxlen=max_history)
        self.request_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.start_time = datetime.now()
        self.lock = threading.Lock()
    
    def collect_system_metrics(self) -> SystemMetrics:
        """Сбор системных метрик"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            connections = len(psutil.net_connections())
            
            metrics = SystemMetrics(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                disk_usage_percent=disk.percent,
                active_connections=connections,
                processing_tasks=0
            )
            
            with self.lock:
                self.system_metrics.append(metrics)
            
            return metrics
        except Exception as e:
            logging.error(f"Ошибка сбора системных метрик: {e}")
            return None
    
    def record_processing(self, operation_type: str, file_size: int, 
                         processing_time: float, success: bool, 
                         error_type: Optional[str] = None):
        """Запись метрик обработки"""
        metrics = ProcessingMetrics(
            timestamp=datetime.now(),
            operation_type=operation_type,
            file_size=file_size,
            processing_time=processing_time,
            success=success,
            error_type=error_type
        )
        
        with self.lock:
            self.processing_metrics.append(metrics)
            self.request_counts[operation_type] += 1
            if not success:
                self.error_counts[error_type or "unknown"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики"""
        with self.lock:
            uptime = datetime.now() - self.start_time
            total_requests = sum(self.request_counts.values())
            total_errors = sum(self.error_counts.values())
            success_rate = ((total_requests - total_errors) / total_requests * 100) if total_requests > 0 else 0
            
            processing_times = {}
            for op_type in set(m.operation_type for m in self.processing_metrics):
                times = [m.processing_time for m in self.processing_metrics if m.operation_type == op_type]
                if times:
                    processing_times[op_type] = {
                        "avg": sum(times) / len(times),
                        "min": min(times),
                        "max": max(times),
                        "count": len(times)
                    }
            
            latest_system = self.system_metrics[-1] if self.system_metrics else None
            
            return {
                "uptime_seconds": uptime.total_seconds(),
                "total_requests": total_requests,
                "total_errors": total_errors,
                "success_rate": success_rate,
                "request_counts": dict(self.request_counts),
                "error_counts": dict(self.error_counts),
                "processing_times": processing_times,
                "system_metrics": asdict(latest_system) if latest_system else None
            }

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

# ---- Initialize Enhanced Components ----
error_handler = ErrorHandler(logger)
security_validator = SecurityValidator()
metrics_collector = MetricsCollector()

# ---- Global error handler ----
@app.errorhandler(Exception)
def handle_error(e):
    error = error_handler.handle_exception(e, f"Route: {request.endpoint}")
    logger.error("Uncaught exception: %s", e, exc_info=True)
    if request.path in ("/upload", "/generate_gcode"):
        return jsonify({
            "success": False, 
            "error": error.user_message,
            "error_type": error.error_type.value,
            "retry_possible": error.retry_possible
        }), 200
    return "Internal Server Error", 500

# ---- Enhanced Utility functions ----
def allowed_file(filename: str) -> bool:
    if not SecurityValidator.validate_filename(filename):
        return False
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

# ---- Enhanced STEP to STL conversion with error handling ----
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

# ---- CAM geometry preparation ----
def prepare_bins(tris, step_xy: float, xmin: float, xmax: float, ymin: float, ymax: float):
    nx = max(16, min(96, int((xmax - xmin) / max(1e-6, step_xy * 2))))
    ny = max(16, min(96, int((ymax - ymin) / max(1e-6, step_xy * 2))))
    sx = (xmax - xmin) / nx if nx > 0 else 1.0
    sy = (ymax - ymin) / ny if ny > 0 else 1.0
    bins = [[[] for _ in range(ny)] for _ in range(nx)]
    coeffs_list = []

    def tri_coeff(tri):
        (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = tri
        ux, uy, uz = x2 - x1, y2 - y1, z2 - z1
        vx, vy, vz = x3 - x1, y3 - y1, z3 - z1
        A = uy * vz - uz * vy
        B = uz * vx - ux * vz
        C = ux * vy - uy * vx
        if abs(C) < 1e-12:
            return None
        D = -(A * x1 + B * y1 + C * z1)
        minx, maxx = min(x1, x2, x3), max(x1, x2, x3)
        miny, maxy = min(y1, y2, y3), max(y1, y2, y3)
        return (A, B, C, D, minx, maxx, miny, maxy, (x1, y1, z1), (x2, y2, z2), (x3, y3, z3))

    for tri in tris:
        c = tri_coeff(tri)
        if c is None:
            continue
        idx = len(coeffs_list)
        coeffs_list.append(c)
        minx, maxx, miny, maxy = c[4:8]
        i0 = int(max(0, min(nx - 1, math.floor((minx - xmin) / sx))))
        i1 = int(max(0, min(nx - 1, math.floor((maxx - xmin) / sx))))
        j0 = int(max(0, min(ny - 1, math.floor((miny - ymin) / sy))))
        j1 = int(max(0, min(ny - 1, math.floor((maxy - ymin) / sy))))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                bins[i][j].append(idx)
    return bins, coeffs_list, nx, ny, sx, sy

def point_in_tri_xy(px: float, py: float, a: Tuple, b: Tuple, c: Tuple) -> bool:
    ax, ay, _ = a
    bx, by, _ = b
    cx, cy, _ = c
    v0x, v0y = cx - ax, cy - ay
    v1x, v1y = bx - ax, by - ay
    v2x, v2y = px - ax, py - ay
    d00 = v0x * v0x + v0y * v0y
    d01 = v0x * v1x + v0y * v1y
    d11 = v1x * v1x + v1y * v1y
    d20 = v2x * v0x + v2y * v0y
    d21 = v2x * v1x + v2y * v1y
    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-12:
        return False
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w
    return u >= -1e-9 and v >= -1e-9 and w >= -1e-9

def z_for(px: float, py: float, coeffs: Tuple) -> Optional[float]:
    A, B, C, D, minx, maxx, miny, maxy, a, b, c = coeffs
    if not (minx - 1e-9 <= px <= maxx + 1e-9 and miny - 1e-9 <= py <= maxy + 1e-9):
        return None
    if not point_in_tri_xy(px, py, a, b, c):
        return None
    return -(A * px + B * py + D) / C

def build_top_sampler(stl_path: Path, step_xy: float) -> Tuple[Tuple, callable]:
    if stlmesh is None:
        raise RuntimeError("numpy-stl not installed")
    m = stlmesh.Mesh.from_file(str(stl_path))
    tris = m.vectors
    xs, ys, zs = m.x, m.y, m.z
    xmin, xmax = float(xs.min()), float(xs.max())
    ymin, ymax = float(ys.min()), float(ys.max())
    zmin, zmax = float(zs.min()), float(zs.max())
    bins, coeffs, nx, ny, sx, sy = prepare_bins(tris, step_xy, xmin, xmax, ymin, ymax)

    def z_func(px: float, py: float) -> Optional[float]:
        i = int(min(nx - 1, max(0, math.floor((px - xmin) / sx))))
        j = int(min(ny - 1, max(0, math.floor((py - ymin) / sy))))
        best = None
        for di in (-1, 0, 1):
            ii = i + di
            if not (0 <= ii < nx):
                continue
            for dj in (-1, 0, 1):
                jj = j + dj
                if not (0 <= jj < ny):
                    continue
                for idx in bins[ii][jj]:
                    z = z_for(px, py, coeffs[idx])
                    if z is not None and (best is None or z > best):
                        best = z
        return best

    return (xmin, xmax, ymin, ymax, zmin, zmax), z_func

# ---- Marching Squares for waterline ----
def marching_squares(Z: List[List[float]], xs: List[float], ys: List[float], level: float) -> List[List[Tuple]]:
    ny, nx = len(Z), len(Z[0]) if Z else 0
    if nx < 2 or ny < 2:
        return []
    segs = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            z00, z10 = Z[j][i], Z[j][i + 1]
            z01, z11 = Z[j + 1][i], Z[j + 1][i + 1]
            c = 0
            if z00 > level:
                c |= 1
            if z10 > level:
                c |= 2
            if z11 > level:
                c |= 4
            if z01 > level:
                c |= 8
            if c == 0 or c == 15:
                continue
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[j], ys[j + 1]

            def interp(a: float, b: float, za: float, zb: float) -> float:
                t = 0.5 if (zb - za) == 0 else (level - za) / ((zb - za) or 1e-9)
                return a + t * (b - a)

            pts = []
            if (c & 1) != (c & 8):
                pts.append((x0, interp(y0, y1, z00, z01)))
            if (c & 2) != (c & 4):
                pts.append((x1, interp(y0, y1, z10, z11)))
            if (c & 1) != (c & 2):
                pts.append((interp(x0, x1, z00, z10), y0))
            if (c & 8) != (c & 4):
                pts.append((interp(x0, x1, z01, z11), y1))
            if len(pts) == 2:
                segs.append((pts[0], pts[1]))
            elif len(pts) == 4:
                segs.append((pts[0], pts[1]))
                segs.append((pts[2], pts[3]))

    loops = []
    used = [False] * len(segs)
    for sidx, (a, b) in enumerate(segs):
        if used[sidx]:
            continue
        used[sidx] = True
        loop = [a, b]
        changed = True
        while changed:
            changed = False
            for k, (p, q) in enumerate(segs):
                if used[k]:
                    continue
                if abs(loop[-1][0] - p[0]) < 1e-6 and abs(loop[-1][1] - p[1]) < 1e-6:
                    loop.append(q)
                    used[k] = True
                    changed = True
                elif abs(loop[-1][0] - q[0]) < 1e-6 and abs(loop[-1][1] - q[1]) < 1e-6:
                    loop.append(p)
                    used[k] = True
                    changed = True
        if len(loop) >= 3:
            loops.append(loop)
    return loops

# ---- Enhanced Controller and operation-specific G-code functions ----
def get_controller_settings(controller: str) -> Dict:
    """Get controller-specific G-code settings"""
    settings = {
        "fanuc": {
            "header": ["G90", "G17", "G21", "G40", "G49", "G80", "G54"],
            "spindle_on": "M3 S{spindle}",
            "spindle_off": "M5",
            "coolant_on": "M8",
            "coolant_off": "M9",
            "rapid": "G0",
            "linear": "G1",
            "program_end": "M30"
        },
        "siemens": {
            "header": ["G90", "G17", "G71", "G40", "G54"],
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
            "header": ["G90", "G17", "G21", "G40", "G49", "G80", "G54"],
            "spindle_on": "M3 S{spindle}",
            "spindle_off": "M5",
            "coolant_on": "M8",
            "coolant_off": "M9",
            "rapid": "G00",
            "linear": "G01",
            "program_end": "M30"
        },
        "mazak": {
            "header": ["G90", "G17", "G21", "G40", "G49", "G80", "G54"],
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

# ---- Enhanced G-code generation with cutting parameters ----
def generate_enhanced_milling_gcode(stl_path: Path, out_path: Path, **params) -> Dict:
    """Enhanced milling G-code generation with cutting parameters calculation"""
    start_time = time.time()
    
    try:
        # Validate and sanitize parameters
        validated_params = SecurityValidator.validate_gcode_params(params)
        
        # Determine material and tool
        material_grade = params.get("material_grade", "42CrMo4")
        material_group = MaterialGroup.P  # Default to steel
        if "al" in material_grade.lower() or "6061" in material_grade:
            material_group = MaterialGroup.N
        elif "stainless" in material_grade.lower() or "316" in material_grade:
            material_group = MaterialGroup.M
        
        material = Material(group=material_group, grade=material_grade)
        tool = Tool(
            type="carbide_endmill",
            diameter=validated_params.get("tool_diam", 3.0),
            flutes=params.get("flutes", 2),
            corner_radius=params.get("corner_radius", 0.0)
        )
        
        # Calculate cutting parameters
        operation_type = params.get("operation_type", "milling")
        cutting_params = CuttingSpeedCalculator.calculate_milling_params(
            material, tool, "roughing" if "rough" in operation_type else "finishing"
        )
        
        controller_settings = get_controller_settings(params.get("controller", "fanuc"))
        
        (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler(stl_path, 0.1)
        
        # Apply allowances
        xmin -= params.get("allowance_x", 0)
        xmax += params.get("allowance_x", 0)
        ymin -= params.get("allowance_y", 0)
        ymax += params.get("allowance_y", 0)
        zmax += params.get("allowance_z", 0)
        
        with open(out_path, "w", encoding="ascii", errors="ignore") as f:
            w = f.write
            w(f"(Generated by CNCera - Enhanced {operation_type.title()} Operation)\n")
            w(f"(Material: {material.grade}, Tool: {tool.diameter}mm, {tool.flutes} flutes)\n")
            w(f"(Vc: {cutting_params.Vc:.1f} m/min, fz: {cutting_params.fz:.3f} mm/tooth)\n")
            w(f"(RPM: {cutting_params.rpm}, Feed: {cutting_params.feed:.1f} mm/min)\n")
            
            for cmd in controller_settings["header"]:
                w(f"{cmd}\n")
            
            if cutting_params.rpm:
                w(f"{controller_settings['spindle_on'].format(spindle=cutting_params.rpm)}\n")
            w(f"{controller_settings['coolant_on']}\n")
            
            clearance = validated_params.get("clearance", 5.0)
            w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
            
            # Enhanced milling strategy
            stepover = validated_params.get("stepover", 0.4)
            step_xy = max(0.1, tool.diameter * stepover)
            
            # Adaptive toolpath
            w("(Adaptive milling strategy)\n")
            center_x = (xmin + xmax) / 2
            center_y = (ymin + ymax) / 2
            max_radius = max(xmax - center_x, ymax - center_y)
            
            w(f"{controller_settings['rapid']} X{center_x:.3f} Y{center_y:.3f}\n")
            w(f"{controller_settings['linear']} Z{zmax:.3f} F{params.get('plunge', 120):.1f}\n")
            w(f"F{cutting_params.feed:.1f}\n")
            
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
            if cutting_params.rpm:
                w(f"{controller_settings['spindle_off']}\n")
            w(f"{controller_settings['program_end']}\n")
        
        processing_time = time.time() - start_time
        metrics_collector.record_processing(
            operation_type, 
            stl_path.stat().st_size, 
            processing_time, 
            True
        )
        
        return {
            "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin, "zmax": zmax},
            "cutting_params": asdict(cutting_params),
            "material": asdict(material),
            "tool": asdict(tool),
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

# ---- Other G-code generation functions ----
def generate_chamfer_gcode(stl_path: Path, out_path: Path, **params) -> Dict:
    """Generate G-code for chamfering operations"""
    controller_settings = get_controller_settings(params.get("controller", "fanuc"))

    (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler(stl_path, 0.1)

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

    (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler(stl_path, 0.5)

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

# Import routes from separate file
exec(open('app_routes.py').read())