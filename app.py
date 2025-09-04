#!/usr/bin/env python3
"""
CNCera - Complete 3D Analysis & G-code Generation Platform
Enhanced with AI analysis, improved Z-origin handling, and integrated G-code preview
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
import glob
import requests
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
from flask import Flask, request, jsonify, send_from_directory, send_file, Response
from werkzeug.utils import secure_filename
from logging.handlers import RotatingFileHandler

# ============================================================================
# G-CODE LINTER (встроенный)
# ============================================================================

class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class LintIssue:
    line: int
    column: int
    severity: Severity
    message: str
    code: str
    suggestion: Optional[str] = None


class GCodeLinter:
    def __init__(self, postprocessor_config: Dict = None):
        self.postprocessor_config = postprocessor_config or {}
        self.issues: List[LintIssue] = []
        self.forbidden_m_codes = {
            "M6", "M19", "M60", "M61", "M62", "M63",
            "M64", "M65", "M66", "M67", "M68", "M69"
        }
        self.required_g_codes = {"G21", "G17", "G90", "G54"}
        self.max_feed_rate = 10000
        self.min_feed_rate = 1
        self.max_rpm = 50000
        self.min_rpm = 1
        self.max_clearance = 100
        self.min_clearance = 0.1
        self.gcode_pattern = re.compile(r'([GMXYZFSP])(-?\d*\.?\d*)')
        self.comment_pattern = re.compile(r'\([^)]*\)|;[^;]*')
        self.line_number_pattern = re.compile(r'^N\d+')

    def lint(self, gcode: str) -> List[LintIssue]:
        """Основная функция линтинга"""
        self.issues = []
        lines = gcode.split('\n')
        for line_num, line in enumerate(lines, 1):
            self._lint_line(line_num, line.strip())
        self._check_file_level_issues(gcode)
        return self.issues

    def _lint_line(self, line_num: int, line: str):
        """Проверка отдельной строки"""
        if not line or line.startswith('(') or line.startswith(';'):
            return
        clean_line = self.comment_pattern.sub('', line).strip()
        if not clean_line:
            return
        self._check_forbidden_codes(line_num, clean_line)
        self._check_parameters(line_num, clean_line)
        self._check_syntax(line_num, clean_line)
        self._check_safety(line_num, clean_line)

    def _check_forbidden_codes(self, line_num: int, line: str):
        """Проверка на запрещённые M-коды"""
        for m_code in self.forbidden_m_codes:
            if m_code in line:
                self.issues.append(LintIssue(
                    line=line_num,
                    column=line.find(m_code),
                    severity=Severity.ERROR,
                    message=f"Запрещённый M-код: {m_code}",
                    code="FORBIDDEN_M_CODE",
                    suggestion=f"Удалите {m_code} или замените на разрешённый код"
                ))

    def _check_parameters(self, line_num: int, line: str):
        """Проверка параметров F, S, координат"""
        f_match = re.search(r'F(\d*\.?\d*)', line)
        if f_match:
            feed_rate = float(f_match.group(1))
            if feed_rate <= 0:
                self.issues.append(LintIssue(
                    line=line_num, column=f_match.start(),
                    severity=Severity.ERROR, message="Нулевая или отрицательная подача",
                    code="ZERO_FEED", suggestion="Установите положительное значение подачи"
                ))
            elif feed_rate > self.max_feed_rate:
                self.issues.append(LintIssue(
                    line=line_num, column=f_match.start(),
                    severity=Severity.WARNING, message=f"Слишком высокая подача: {feed_rate}",
                    code="HIGH_FEED", suggestion=f"Максимальная подача: {self.max_feed_rate}"
                ))
            elif feed_rate < self.min_feed_rate:
                self.issues.append(LintIssue(
                    line=line_num, column=f_match.start(),
                    severity=Severity.WARNING, message=f"Слишком низкая подача: {feed_rate}",
                    code="LOW_FEED", suggestion=f"Минимальная подача: {self.min_feed_rate}"
                ))

        s_match = re.search(r'S(\d*\.?\d*)', line)
        if s_match:
            rpm = float(s_match.group(1))
            if rpm <= 0:
                self.issues.append(LintIssue(
                    line=line_num, column=s_match.start(),
                    severity=Severity.ERROR, message="Нулевая или отрицательная скорость шпинделя",
                    code="ZERO_RPM", suggestion="Установите положительное значение RPM"
                ))
            elif rpm > self.max_rpm:
                self.issues.append(LintIssue(
                    line=line_num, column=s_match.start(),
                    severity=Severity.WARNING, message=f"Слишком высокая скорость шпинделя: {rpm}",
                    code="HIGH_RPM", suggestion=f"Максимальная скорость: {self.max_rpm}"
                ))
            elif rpm < self.min_rpm:
                self.issues.append(LintIssue(
                    line=line_num, column=s_match.start(),
                    severity=Severity.WARNING, message=f"Слишком низкая скорость шпинделя: {rpm}",
                    code="LOW_RPM", suggestion=f"Минимальная скорость: {self.min_rpm}"
                ))

        z_match = re.search(r'Z(-?\d*\.?\d*)', line)
        if z_match:
            z_value = float(z_match.group(1))
            if z_value < -self.max_clearance:
                self.issues.append(LintIssue(
                    line=line_num, column=z_match.start(),
                    severity=Severity.WARNING, message=f"Z-координата слишком низкая: {z_value}",
                    code="LOW_Z", suggestion=f"Проверьте безопасность, минимум: {-self.max_clearance}"
                ))

    def _check_syntax(self, line_num: int, line: str):
        """Проверка синтаксиса G-кода"""
        if re.search(r'M[34]', line) and not re.search(r'S\d', line):
            self.issues.append(LintIssue(
                line=line_num, column=0, severity=Severity.ERROR,
                message="Отсутствует скорость шпинделя при M3/M4",
                code="MISSING_S", suggestion="Добавьте S-параметр с скоростью шпинделя"
            ))
        if re.search(r'G1', line) and not re.search(r'F\d', line):
            self.issues.append(LintIssue(
                line=line_num, column=0, severity=Severity.ERROR,
                message="Отсутствует подача при G1",
                code="MISSING_F", suggestion="Добавьте F-параметр с подачей"
            ))
        invalid_g_codes = re.findall(r'G(\d+)', line)
        for g_code in invalid_g_codes:
            if not self._is_valid_g_code(g_code):
                self.issues.append(LintIssue(
                    line=line_num, column=line.find(f'G{g_code}'),
                    severity=Severity.ERROR, message=f"Некорректный G-код: G{g_code}",
                    code="INVALID_G_CODE", suggestion="Проверьте правильность G-кода"
                ))

    def _check_safety(self, line_num: int, line: str):
        """Проверка безопасности"""
        if re.search(r'G0.*Z', line) and not re.search(r'G0.*Z\d+\.\d+', line):
            self.issues.append(LintIssue(
                line=line_num, column=0, severity=Severity.WARNING,
                message="Быстрое движение по Z без указания координаты",
                code="RAPID_Z_MOVEMENT", suggestion="Убедитесь в безопасности быстрого движения по Z"
            ))

    def _check_file_level_issues(self, gcode: str):
        """Проверки на уровне всего файла"""
        for required_code in self.required_g_codes:
            if required_code not in gcode:
                self.issues.append(LintIssue(
                    line=1, column=0, severity=Severity.WARNING,
                    message=f"Отсутствует обязательный код: {required_code}",
                    code="MISSING_REQUIRED_CODE", suggestion=f"Добавьте {required_code} в начало программы"
                ))
        if not gcode.strip().endswith('M30') and 'M30' not in gcode:
            self.issues.append(LintIssue(
                line=1, column=0, severity=Severity.WARNING,
                message="Отсутствует M30 в конце программы",
                code="MISSING_M30", suggestion="Добавьте M30 в конец программы"
            ))

    def _is_valid_g_code(self, g_code: str) -> bool:
        """Проверка валидности G-кода"""
        valid_g_codes = {
            "0", "1", "2", "3", "4", "17", "18", "19", "20", "21", "28", "30", "40", "41", "42", "43", "44", "49",
            "54", "55", "56", "57", "58", "59", "80", "81", "82", "83", "84", "85", "86", "87", "88", "89",
            "90", "91", "92", "93", "94", "95", "96", "97", "98", "99"
        }
        return g_code in valid_g_codes

    def get_metrics(self, gcode: str) -> Dict:
        """Получение метрик G-кода"""
        lines = gcode.split('\n')
        non_empty_lines = [line for line in lines if line.strip() and not line.strip().startswith(('(', ';'))]
        rapid_moves = len(re.findall(r'G0', gcode))
        linear_moves = len(re.findall(r'G1', gcode))
        arc_moves = len(re.findall(r'G[23]', gcode))
        x_coords = [float(m.group(1)) for m in re.finditer(r'X(-?\d*\.?\d*)', gcode)]
        y_coords = [float(m.group(1)) for m in re.finditer(r'Y(-?\d*\.?\d*)', gcode)]
        z_coords = [float(m.group(1)) for m in re.finditer(r'Z(-?\d*\.?\d*)', gcode)]
        x_range = (min(x_coords), max(x_coords)) if x_coords else (0, 0)
        y_range = (min(y_coords), max(y_coords)) if y_coords else (0, 0)
        z_range = (min(z_coords), max(z_coords)) if z_coords else (0, 0)
        total_length = 0
        if len(x_coords) > 1:
            for i in range(1, len(x_coords)):
                dx = x_coords[i] - x_coords[i - 1]
                dy = y_coords[i] - y_coords[i - 1] if i < len(y_coords) else 0
                dz = z_coords[i] - z_coords[i - 1] if i < len(z_coords) else 0
                total_length += math.sqrt(dx * dx + dy * dy + dz * dz)
        return {
            "total_lines": len(non_empty_lines), "rapid_moves": rapid_moves, "linear_moves": linear_moves,
            "arc_moves": arc_moves, "x_range": x_range, "y_range": y_range, "z_range": z_range,
            "total_length": total_length, "issues_count": len(self.issues),
            "errors_count": len([i for i in self.issues if i.severity == Severity.ERROR]),
            "warnings_count": len([i for i in self.issues if i.severity == Severity.WARNING])
        }


def validate_gcode(gcode: str, postprocessor_id: str = None) -> Dict:
    """Валидация G-кода с учётом постпроцессора"""
    linter = GCodeLinter()
    issues = linter.lint(gcode)
    metrics = linter.get_metrics(gcode)
    return {
        "valid": len([i for i in issues if i.severity == Severity.ERROR]) == 0,
        "issues": [{
            "line": issue.line, "column": issue.column, "severity": issue.severity.value,
            "message": issue.message, "code": issue.code, "suggestion": issue.suggestion
        } for issue in issues], "metrics": metrics
    }


# ============================================================================
# AI ANALYSIS MODULE
# ============================================================================

class AIProvider:
    def __init__(self):
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        self.grok_key = os.environ.get("GROK_API_KEY")
        self.timeout = 12

    def get_provider(self) -> Tuple[str, str]:
        """Get preferred AI provider and model"""
        if self.openai_key:
            return "openai", "gpt-4o-mini"
        elif self.anthropic_key:
            return "anthropic", "claude-3-haiku-20240307"
        elif self.grok_key:
            return "grok", "grok-beta"
        return None, None

    def call_ai(self, prompt: str, model: str = None) -> Dict:
        """Call AI provider with timeout and error handling"""
        provider, default_model = self.get_provider()
        if not provider:
            return {"success": False, "error": "No AI provider configured"}
        
        model = model or default_model
        
        try:
            if provider == "openai":
                return self._call_openai(prompt, model)
            elif provider == "anthropic":
                return self._call_anthropic(prompt, model)
            elif provider == "grok":
                return self._call_grok(prompt, model)
        except Exception as e:
            logger.warning(f"AI call failed: {e}")
            return {"success": False, "error": f"AI service error: {str(e)}"}

    def _call_openai(self, prompt: str, model: str) -> Dict:
        """Call OpenAI API"""
        headers = {"Authorization": f"Bearer {self.openai_key}", "Content-Type": "application/json"}
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
            "temperature": 0.3
        }
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers, json=data, timeout=self.timeout
        )
        if response.status_code == 200:
            result = response.json()
            return {
                "success": True,
                "answer": result["choices"][0]["message"]["content"],
                "provider": "openai",
                "model": model
            }
        return {"success": False, "error": f"OpenAI API error: {response.status_code}"}

    def _call_anthropic(self, prompt: str, model: str) -> Dict:
        """Call Anthropic API"""
        headers = {
            "x-api-key": self.anthropic_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        data = {
            "model": model,
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}]
        }
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers, json=data, timeout=self.timeout
        )
        if response.status_code == 200:
            result = response.json()
            return {
                "success": True,
                "answer": result["content"][0]["text"],
                "provider": "anthropic",
                "model": model
            }
        return {"success": False, "error": f"Anthropic API error: {response.status_code}"}

    def _call_grok(self, prompt: str, model: str) -> Dict:
        """Call Grok API (placeholder - would need actual implementation)"""
        return {"success": False, "error": "Grok API not implemented"}


ai_provider = AIProvider()


def analyze_model_with_ai(geometry: Dict, bbox: Dict, units: str, controller: str, operation_type: str, tool: Dict = None) -> Dict:
    """Analyze 3D model with AI for machining recommendations"""
    prompt = f"""
Analyze this 3D model for CNC machining:

Geometry: {json.dumps(geometry, indent=2)}
Bounding box: {json.dumps(bbox, indent=2)}
Units: {units}
Controller: {controller}
Operation: {operation_type}
Tool: {json.dumps(tool or {}, indent=2)}

Provide analysis in JSON format:
{{
    "findings": {{
        "zmin": <minimum Z coordinate>,
        "zmax": <maximum Z coordinate>,
        "thickness": <part thickness>,
        "flatness": <surface flatness assessment>,
        "holes": [<list of hole features>],
        "risks": [<list of machining risks>]
    }},
    "suggestions": {{
        "origin": <recommended origin point>,
        "stepover": <recommended stepover ratio>,
        "stepdown": <recommended stepdown value>,
        "feeds_speeds": <recommended feeds and speeds>,
        "clamps": <clamping recommendations>
    }}
}}
"""
    result = ai_provider.call_ai(prompt)
    if result["success"]:
        try:
            # Try to parse AI response as JSON
            ai_data = json.loads(result["answer"])
            return {"success": True, "findings": ai_data.get("findings", {}), "suggestions": ai_data.get("suggestions", {})}
        except:
            # Fallback to text response
            return {"success": True, "findings": {}, "suggestions": {"note": result["answer"]}}
    return result


def analyze_gcode_with_ai(gcode: str, controller: str, material: str = None, tool: str = None) -> Dict:
    """Analyze G-code with AI for optimization suggestions"""
    # Get linter results first
    linter_result = validate_gcode(gcode, controller)
    
    prompt = f"""
Analyze this G-code for CNC machining optimization:

Controller: {controller}
Material: {material or "Unknown"}
Tool: {tool or "Unknown"}
G-code (first 50 lines):
{chr(10).join(gcode.split(chr(10))[:50])}

Linter results: {json.dumps(linter_result, indent=2)}

Provide analysis in JSON format:
{{
    "summary": <brief summary of the G-code>,
    "risks": [<list of potential issues>],
    "suggestions": [<list of optimization suggestions>]
}}
"""
    result = ai_provider.call_ai(prompt)
    if result["success"]:
        try:
            ai_data = json.loads(result["answer"])
            return {
                "success": True,
                "summary": ai_data.get("summary", ""),
                "risks": ai_data.get("risks", []),
                "suggestions": ai_data.get("suggestions", []),
                "linter": linter_result
            }
        except:
            return {
                "success": True,
                "summary": result["answer"],
                "risks": [],
                "suggestions": [],
                "linter": linter_result
            }
    return result


# ============================================================================
# SERVER-SIDE PNG RENDERING (fallback)
# ============================================================================

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

# ============================================================================
# LOGGING SETUP WITH ROTATION
# ============================================================================

LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

file_handler = RotatingFileHandler(
    LOGS_DIR / "server.log", maxBytes=5*1024*1024, backupCount=3
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s"
))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s"
))

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger("CNCera")

# ============================================================================
# DIRECTORY SETUP
# ============================================================================

BASE = Path(__file__).parent.resolve()
TEMP = BASE / "temp"
TEMP.mkdir(exist_ok=True)
MODELS = BASE / "models"
MODELS.mkdir(exist_ok=True)
STATIC = BASE / "static"
STATIC.mkdir(exist_ok=True)
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".step", ".stp", ".stl"}

# Initialize Flask with explicit static configuration
app = Flask(
    __name__,
    static_folder=str(BASE / "static"),
    static_url_path="/static"
)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB limit
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600

# ============================================================================
# CACHING FOR FREECADCMD
# ============================================================================

_freecadcmd_cache = None

def get_freecadcmd_path() -> Optional[str]:
    """Get FreeCADCmd path with caching"""
    global _freecadcmd_cache
    if _freecadcmd_cache is not None:
        return _freecadcmd_cache
    _freecadcmd_cache = locate_freecadcmd()
    return _freecadcmd_cache

# ============================================================================
# GLOBAL ERROR HANDLER
# ============================================================================

API_ENDPOINTS = {
    "/upload", "/generate_gcode", "/calculate_parameters", 
    "/validate_gcode", "/materials", "/tools", "/postprocessors", 
    "/download_gcode", "/download_results", "/healthz",
    "/ai/inspect_model", "/ai/analyze_gcode", "/ai/ask"
}

@app.errorhandler(Exception)
def handle_error(e):
    # Handle static file 404s without escalating to 500
    if hasattr(e, 'code') and e.code == 404 and request.path.startswith("/static/"):
        logger.warning("Static file not found: %s", request.path)
        return f"Static file not found: {request.path}", 404
    
    # Log other exceptions as errors
    logger.error("Uncaught exception: %s", e, exc_info=True)
    
    # Return JSON for API endpoints
    if request.path in API_ENDPOINTS:
        return jsonify({"success": False, "error": f"Critical error: {e.__class__.__name__}: {str(e)}"}), 200
    
    # Return HTML error page for UI routes
    error_html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Error - CNCera</title>
    <style>body{{font-family:Arial,sans-serif;margin:40px;background:#f5f5f5}}
    .error{{background:white;padding:20px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1)}}
    h1{{color:#d32f2f}}</style></head>
    <body><div class="error"><h1>Internal Server Error</h1>
    <p>An unexpected error occurred. Please try again later.</p>
    <p>Error: {str(e)}</p></div></body></html>"""
    return error_html, 500

# ============================================================================
# STATIC FILE MANAGEMENT
# ============================================================================

def ensure_static_files():
    """Ensure required static files exist, create placeholders if missing"""
    required_files = [
        ("static/js/app.js", """// CNCera App JS - Placeholder
console.log("CNCera App JS loaded (placeholder)");
// This is a placeholder file created automatically
// Replace with actual app.js content"""),
        ("static/js/ncviewer.js", """// NC Viewer - Placeholder
console.log("NC Viewer JS loaded (placeholder)");
window.NCViewer = class NCViewer {
    constructor(container) {
        console.log("NC Viewer placeholder initialized");
        container.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">NC Viewer placeholder - WebGL not available</div>';
    }
    loadGcode(gcode) {
        console.log("G-code loaded in placeholder viewer");
    }
};""")
    ]
    
    for file_path, content in required_files:
        full_path = BASE / file_path
        if not full_path.exists():
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            logger.warning("Missing static asset created: %s", file_path)

# Ensure static files exist on startup
ensure_static_files()

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

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

def validate_api_params(data: Dict) -> Tuple[bool, str]:
    """Validate API parameters for dir_axis and origin"""
    dir_axis = data.get("dir", "X")
    if dir_axis.upper() not in ["X", "Y"]:
        return False, f"Invalid dir_axis: {dir_axis}. Must be 'X' or 'Y'"
    origin = data.get("origin", "bbox_min")
    valid_origins = ["bbox_min", "bbox_center", "bbox_top_center"]
    if origin not in valid_origins:
        return False, f"Invalid origin: {origin}. Must be one of: {', '.join(valid_origins)}"
    return True, ""

def secure_filename_check(filename: str) -> bool:
    """Check if filename is safe (no path traversal)"""
    if not filename:
        return False
    dangerous_chars = ['..', '/', '\\']
    for char in dangerous_chars:
        if char in filename:
            return False
    return True

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
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(pos, 0)
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

# ============================================================================
# CLEANUP FUNCTIONS
# ============================================================================

def cleanup_old_files():
    """Clean up old files in temp/ and models/ directories"""
    current_time = time.time()
    max_age = 24 * 60 * 60  # 24 hours in seconds
    for directory in [TEMP, MODELS]:
        try:
            for file_path in directory.iterdir():
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age:
                        try:
                            file_path.unlink()
                            logger.info(f"Cleaned up old file: {file_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete {file_path}: {e}")
        except Exception as e:
            logger.warning(f"Failed to clean up {directory}: {e}")

@app.before_request
def before_request():
    """Run before each request - cleanup old files every 10 minutes"""
    if not hasattr(app, '_last_cleanup'):
        app._last_cleanup = 0
    current_time = time.time()
    if current_time - app._last_cleanup > 600:  # 10 minutes
        cleanup_old_files()
        app._last_cleanup = current_time

# ============================================================================
# DATA LOADING FUNCTIONS
# ============================================================================

def load_materials() -> Dict:
    """Load materials configuration"""
    try:
        with open(DATA / "materials.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load materials: {e}")
        return {"materials": [], "groups": []}

def load_tools() -> Dict:
    """Load tools configuration"""
    try:
        with open(DATA / "tools.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load tools: {e}")
        return {"tools": [], "tool_types": [], "materials": [], "coatings": []}

def load_postprocessors() -> Dict:
    """Load postprocessors configuration"""
    try:
        with open(DATA / "postprocessors.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load postprocessors: {e}")
        return {"postprocessors": [], "controller_groups": [], "validation_rules": {}}

# ============================================================================
# MATERIAL CALCULATIONS
# ============================================================================

def calculate_cutting_parameters(material_id: str, tool_id: str) -> Dict:
    """Calculate cutting parameters based on material and tool"""
    materials = load_materials()
    tools = load_tools()
    material = next((m for m in materials["materials"] if m["id"] == material_id), None)
    tool = next((t for t in tools["tools"] if t["id"] == tool_id), None)
    if not material or not tool:
        return {}
    vc_range = material.get("vc_m_per_min", [200, 400])
    fz_range = material.get("fz_mm_per_tooth", [0.05, 0.15])
    vc = (vc_range[0] + vc_range[-1]) / 2
    fz = (fz_range[0] + fz_range[-1]) / 2
    tool_diam = tool["diam_mm"]
    flutes = tool["flutes"]
    rpm = int(1000 * vc / (math.pi * tool_diam))
    feed = fz * flutes * rpm
    max_rpm = tool.get("max_rpm", 20000)
    max_feed = tool.get("max_feed", 2000)
    rpm = min(rpm, max_rpm)
    feed = min(feed, max_feed)
    return {
        "rpm": rpm, "feed": feed, "plunge": feed * 0.4,
        "stepover": tool_diam * 0.4, "stepdown": tool_diam * 0.5
    }

# ============================================================================
# STL MESH ANALYSIS
# ============================================================================

def analyze_stl(stl_path: Path) -> Dict:
    if stlmesh is None:
        return {"vertices": 0, "faces": 0}
    try:
        mesh = stlmesh.Mesh.from_file(str(stl_path))
        return {"vertices": len(mesh.vectors) * 3, "faces": len(mesh.vectors)}
    except Exception as e:
        logger.warning(f"STL analysis failed: {e}")
        return {"vertices": 0, "faces": 0}

# ============================================================================
# PNG RENDERING FOR STL
# ============================================================================

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

# ============================================================================
# LOCATE FREECADCMD
# ============================================================================

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
        "/usr/bin/FreeCADCmd", "/usr/local/bin/FreeCADCmd",
        "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd"
    ]
    for pattern in patterns:
        matches = glob.glob(pattern)
        for match in matches:
            if os.path.isfile(match):
                return match
    return None

# ============================================================================
# STEP TO STL CONVERSION
# ============================================================================

def freecad_export_step_to_stl(
        step_path: Path, stl_path: Path, linear_deflection: float = 0.1,
        angular_deflection_deg: float = 15.0, relative: bool = False, units: str = "auto"
) -> Dict:
    exe = get_freecadcmd_path()
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
            [exe, str(tmp_py)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=600, creationflags=creationflags, env=env
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

# ============================================================================
# CAM GEOMETRY PREPARATION
# ============================================================================

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

# ============================================================================
# MARCHING SQUARES FOR WATERLINE
# ============================================================================

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
            if z00 > level: c |= 1
            if z10 > level: c |= 2
            if z11 > level: c |= 4
            if z01 > level: c |= 8
            if c == 0 or c == 15: continue
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[j], ys[j + 1]

            def interp(a: float, b: float, za: float, zb: float) -> float:
                t = 0.5 if (zb - za) == 0 else (level - za) / ((zb - za) or 1e-9)
                return a + t * (b - a)

            pts = []
            if (c & 1) != (c & 8): pts.append((x0, interp(y0, y1, z00, z01)))
            if (c & 2) != (c & 4): pts.append((x1, interp(y0, y1, z10, z11)))
            if (c & 1) != (c & 2): pts.append((interp(x0, x1, z00, z10), y0))
            if (c & 8) != (c & 4): pts.append((interp(x0, x1, z01, z11), y1))
            if len(pts) == 2: segs.append((pts[0], pts[1]))
            elif len(pts) == 4: segs.append((pts[0], pts[1])); segs.append((pts[2], pts[3]))

    loops = []
    used = [False] * len(segs)
    for sidx, (a, b) in enumerate(segs):
        if used[sidx]: continue
        used[sidx] = True
        loop = [a, b]
        changed = True
        while changed:
            changed = False
            for k, (p, q) in enumerate(segs):
                if used[k]: continue
                if abs(loop[-1][0] - p[0]) < 1e-6 and abs(loop[-1][1] - p[1]) < 1e-6:
                    loop.append(q); used[k] = True; changed = True
                elif abs(loop[-1][0] - q[0]) < 1e-6 and abs(loop[-1][1] - q[1]) < 1e-6:
                    loop.append(p); used[k] = True; changed = True
        if len(loop) >= 3: loops.append(loop)
    return loops

# ============================================================================
# CONTROLLER AND OPERATION-SPECIFIC G-CODE FUNCTIONS
# ============================================================================

def get_controller_settings(controller: str) -> Dict:
    """Get controller-specific G-code settings"""
    postprocessors = load_postprocessors()
    controller_map = {pp["id"]: pp for pp in postprocessors["postprocessors"]}
    if controller in controller_map:
        return controller_map[controller]
    return {
        "id": "fanuc_metric", "name": "Fanuc (метрическая)", "controller": "Fanuc",
        "header": "(Generated by CNCera - Fanuc)\nG90 G17 G21 G94\nG54\n",
        "footer": "M5\nG91 G28 Z0\nG28 X0 Y0\nM30\n",
        "rapid": "G0", "linear": "G1", "coolant_on": "M8", "coolant_off": "M9",
        "spindle_on": "M3 S{rpm}", "spindle_off": "M5"
    }

def deduplicate_gcode_lines(gcode_lines: List[str]) -> List[str]:
    """Remove duplicate consecutive lines and redundant modal repeats"""
    if not gcode_lines:
        return []
    
    result = []
    last_line = None
    last_xyz = None
    modal_g = None
    modal_m = None
    
    for line in gcode_lines:
        line = line.strip()
        if not line or line.startswith('(') or line.startswith(';'):
            result.append(line)
            continue
            
        # Check for exact duplicates
        if line == last_line:
            continue
            
        # Check for redundant XYZ coordinates
        xyz_match = re.search(r'[XY](-?\d*\.?\d*)', line)
        if xyz_match and last_xyz and line == last_xyz:
            continue
            
        # Check for redundant modal G codes
        g_match = re.search(r'G(\d+)', line)
        if g_match and modal_g and g_match.group(1) == modal_g:
            # Remove the G code from the line
            line = re.sub(r'G\d+\s*', '', line).strip()
            if not line:
                continue
                
        # Check for redundant modal M codes
        m_match = re.search(r'M(\d+)', line)
        if m_match and modal_m and m_match.group(1) == modal_m:
            # Remove the M code from the line
            line = re.sub(r'M\d+\s*', '', line).strip()
            if not line:
                continue
        
        result.append(line)
        last_line = line
        last_xyz = line if xyz_match else last_xyz
        
        if g_match:
            modal_g = g_match.group(1)
        if m_match:
            modal_m = m_match.group(1)
    
    return result

def generate_raster_gcode(
        stl_path: Path, out_path: Path, tool_diam: float = 3.0, stepover: float = 0.4,
        feed: float = 300.0, plunge: float = 120.0, clearance: float = 5.0,
        spindle: Optional[int] = 8000, dir_axis: str = "X", origin: str = "bbox_min",
        stepdown: float = 0.0, feed_rough: Optional[float] = None, feed_finish: Optional[float] = None,
        finish_stepover: Optional[float] = None, waterline: bool = False, waterline_dz: float = 0.0,
        allowance_x: float = 0.0, allowance_y: float = 0.0, allowance_z: float = 0.0,
        controller: str = "fanuc_metric", operation_type: str = "milling"
) -> Dict:
    tool_diam = validate_float(tool_diam, 3.0, 0.1, 50.0)
    stepover = validate_float(stepover, 0.4, 0.05, 0.95)
    feed = validate_float(feed, 300.0, 10.0, 5000.0)
    plunge = validate_float(plunge, 120.0, 10.0, 2000.0)
    clearance = validate_float(clearance, 5.0, 1.0, 50.0)
    spindle = validate_int(spindle, 8000, 1000, 24000) if spindle else None
    stepdown = validate_float(stepdown, 0.0, 0.0, 50.0)
    feed_rough = validate_float(feed_rough, feed, 10.0, 5000.0) if feed_rough else feed
    feed_finish = validate_float(feed_finish, feed, 10.0, 5000.0) if feed_finish else feed
    finish_stepover = validate_float(finish_stepover, stepover, 0.05, 0.95) if finish_stepover else stepover
    waterline_dz = validate_float(waterline_dz, 0.0, 0.0, 50.0)

    step_xy = max(0.1, tool_diam * stepover)
    (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler(stl_path, step_xy)

    # Apply allowances to geometry bounds
    xmin -= allowance_x; xmax += allowance_x
    ymin -= allowance_y; ymax += allowance_y
    zmax += allowance_z

    def estimate_cost(step: float) -> int:
        nx = max(2, int(math.ceil((xmax - xmin) / step)) + 1)
        ny = max(2, int(math.ceil((ymax - ymin) / step)) + 1)
        return nx * ny

    MAX_POINTS = 40000
    points = estimate_cost(step_xy)
    while points > MAX_POINTS:
        step_xy *= 1.3
        points = estimate_cost(step_xy)

    nx = max(2, int(math.ceil((xmax - xmin) / step_xy)) + 1)
    ny = max(2, int(math.ceil((ymax - ymin) / step_xy)) + 1)

    # FIXED: Correct Z-origin handling
    origin = origin if origin in ("bbox_min", "bbox_center", "bbox_top_center") else "bbox_min"
    ox, oy, oz = {
        "bbox_min": (xmin, ymin, zmin),
        "bbox_center": ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0, zmin),
        "bbox_top_center": ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0, zmax)
    }[origin]

    controller_settings = get_controller_settings(controller)

    def zigzag_lines():
        lines = []
        dir_axis_upper = dir_axis.upper()
        if dir_axis_upper == "X":
            ys = [ymin + i * step_xy for i in range(ny)]
            for j, y in enumerate(ys):
                xs = [xmin + i * step_xy for i in range(nx)]
                if j % 2 == 1: xs.reverse()
                lines.append([(x, y) for x in xs])
        else:
            xs = [xmin + i * step_xy for i in range(nx)]
            for i, x in enumerate(xs):
                ys = [ymin + j * step_xy for j in range(ny)]
                if i % 2 == 1: ys.reverse()
                lines.append([(x, y) for y in ys])
        return lines

    def sample_height_grid(step: float):
        xs = [xmin + i * step for i in range(nx)]
        ys = [ymin + j * step for j in range(ny)]
        Z = [[z_func(x, y) or -1e12 for x in xs] for y in ys]
        return xs, ys, Z

    # Collect all G-code lines for deduplication
    gcode_lines = []
    
    def w(line: str):
        gcode_lines.append(line)

    w(f"(Generated by CNCera - {operation_type.title()} - {controller_settings['controller'].upper()})")
    w(f"(Origin: {origin})")
    w("")
    
    for cmd in controller_settings["header"].split('\n'):
        if cmd.strip():
            w(cmd)

    if spindle: w(controller_settings['spindle_on'].format(rpm=spindle))
    w(controller_settings['coolant_on'])
    w(f"{controller_settings['rapid']} Z{clearance:.3f}")

    if stepdown > 0:
        zL = zmax
        while zL > zmin + 0.5 * stepdown:
            zL -= stepdown
            w(f"(Rough level Z={zL - oz:.3f})")
            for line in zigzag_lines():
                x0, y0 = line[0]
                w(f"{controller_settings['rapid']} X{(x0 - ox):.3f} Y{(y0 - oy):.3f}")
                z0 = z_func(x0, y0)
                if z0 is not None:
                    # FIXED: Clamp Z to part bounds with allowance
                    zt = min(z0, zL)
                    zt = max(zt, zmin - abs(allowance_z))  # Never go below part
                    w(f"{controller_settings['linear']} Z{(zt - oz):.3f} F{plunge:.1f}")
                    w(f"F{feed_rough:.1f}")
                else:
                    w(f"{controller_settings['rapid']} Z{clearance:.3f}")
                for x, y in line[1:]:
                    z = z_func(x, y)
                    if z is None:
                        w(f"{controller_settings['rapid']} Z{clearance:.3f}")
                        w(f"{controller_settings['rapid']} X{(x - ox):.3f} Y{(y - oy):.3f}")
                    else:
                        # FIXED: Clamp Z to part bounds with allowance
                        zt = min(z, zL)
                        zt = max(zt, zmin - abs(allowance_z))  # Never go below part
                        w(f"{controller_settings['linear']} X{(x - ox):.3f} Y{(y - oy):.3f} Z{(zt - oz):.3f}")
            w(f"{controller_settings['rapid']} Z{clearance:.3f}")

    if finish_stepover != stepover:
        step_fin_xy = max(0.05, tool_diam * finish_stepover)
        if step_fin_xy != step_xy:
            (xmin, xmax, ymin, ymax, _, _), z_func = build_top_sampler(stl_path, step_fin_xy)
            xmin -= allowance_x; xmax += allowance_x; ymin -= allowance_y; ymax += allowance_y
            nx = max(2, int(math.ceil((xmax - xmin) / step_fin_xy)) + 1)
            ny = max(2, int(math.ceil((ymax - ymin) / step_fin_xy)) + 1)

    w("(Finish pass)")
    for line in zigzag_lines():
        x0, y0 = line[0]
        w(f"{controller_settings['rapid']} X{(x0 - ox):.3f} Y{(y0 - oy):.3f}")
        z0 = z_func(x0, y0)
        if z0 is not None:
            # FIXED: Clamp Z to part bounds with allowance
            zt = max(z0, zmin - abs(allowance_z))  # Never go below part
            w(f"{controller_settings['linear']} Z{(zt - oz):.3f} F{plunge:.1f}")
            w(f"F{feed_finish:.1f}")
        else:
            w(f"{controller_settings['rapid']} Z{clearance:.3f}")
        for x, y in line[1:]:
            z = z_func(x, y)
            if z is None:
                w(f"{controller_settings['rapid']} Z{clearance:.3f}")
                w(f"{controller_settings['rapid']} X{(x - ox):.3f} Y{(y - oy):.3f}")
            else:
                # FIXED: Clamp Z to part bounds with allowance
                zt = max(z, zmin - abs(allowance_z))  # Never go below part
                w(f"{controller_settings['linear']} X{(x - ox):.3f} Y{(y - oy):.3f} Z{(zt - oz):.3f}")
    w(f"{controller_settings['rapid']} Z{clearance:.3f}")

    if waterline and waterline_dz > 0:
        w("(Waterline)")
        xs, ys, Z = sample_height_grid(max(step_xy, tool_diam * 0.6))
        cur = zmax
        while cur > zmin + 0.5 * waterline_dz:
            cur -= waterline_dz
            loops = marching_squares(Z, xs, ys, cur)
            for loop in loops:
                sx, sy = loop[0]
                w(f"{controller_settings['rapid']} X{(sx - ox):.3f} Y{(sy - oy):.3f} Z{clearance:.3f}")
                w(f"{controller_settings['linear']} Z{(cur - oz):.3f} F{plunge:.1f}")
                w(f"F{feed_finish:.1f}")
                for x, y in loop[1:]:
                    w(f"{controller_settings['linear']} X{(x - ox):.3f} Y{(y - oy):.3f} Z{(cur - oz):.3f}")
                w(f"{controller_settings['rapid']} Z{clearance:.3f}")

    w(controller_settings['coolant_off'])
    if spindle: w(controller_settings['spindle_off'])
    w(controller_settings["footer"])

    # Deduplicate G-code lines
    deduplicated_lines = deduplicate_gcode_lines(gcode_lines)
    
    # Write final G-code
    with open(out_path, "w", encoding="ascii", errors="ignore") as f:
        for line in deduplicated_lines:
            f.write(line + "\n")

    return {
        "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin, "zmax": zmax},
        "grid": {"nx": nx, "ny": ny, "step_xy": step_xy},
        "origin": {"ox": ox, "oy": oy, "oz": oz}
    }

# ============================================================================
# API ROUTES
# ============================================================================

@app.route("/healthz")
def healthz():
    """Health check endpoint"""
    return jsonify({"ok": True, "time": time.time()})

@app.route("/materials")
def get_materials():
    """Get materials list"""
    materials = load_materials()
    return jsonify(materials)

@app.route("/tools")
def get_tools():
    """Get tools list"""
    tools = load_tools()
    return jsonify(tools)

@app.route("/postprocessors")
def get_postprocessors():
    """Get postprocessors list"""
    postprocessors = load_postprocessors()
    return jsonify(postprocessors)

@app.route("/calculate_parameters", methods=["POST"])
def calculate_parameters():
    """Calculate cutting parameters based on material and tool"""
    try:
        data = request.get_json()
        material_id = data.get("material_id")
        tool_id = data.get("tool_id")
        if not material_id or not tool_id:
            return jsonify({"success": False, "error": "Missing material_id or tool_id"})
        params = calculate_cutting_parameters(material_id, tool_id)
        return jsonify({"success": True, "parameters": params})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/validate_gcode", methods=["POST"])
def validate_gcode_endpoint():
    """Validate G-code using linter"""
    try:
        data = request.get_json()
        gcode = data.get("gcode", "")
        postprocessor_id = data.get("postprocessor_id")
        if not gcode:
            return jsonify({"success": False, "error": "No G-code provided"})
        result = validate_gcode(gcode, postprocessor_id)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ============================================================================
# AI ANALYSIS ROUTES
# ============================================================================

@app.route("/ai/inspect_model", methods=["POST"])
def ai_inspect_model():
    """AI analysis of 3D model for machining recommendations"""
    try:
        data = request.get_json()
        geometry = data.get("geometry", {})
        bbox = data.get("bbox", {})
        units = data.get("units", "mm")
        controller = data.get("controller", "fanuc")
        operation_type = data.get("operation_type", "milling")
        tool = data.get("tool", {})
        
        result = analyze_model_with_ai(geometry, bbox, units, controller, operation_type, tool)
        return jsonify(result)
    except Exception as e:
        logger.warning(f"AI model inspection failed: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/ai/analyze_gcode", methods=["POST"])
def ai_analyze_gcode():
    """AI analysis of G-code for optimization suggestions"""
    try:
        data = request.get_json()
        gcode = data.get("gcode", "")
        controller = data.get("controller", "fanuc")
        material = data.get("material")
        tool = data.get("tool")
        
        if not gcode:
            return jsonify({"success": False, "error": "No G-code provided"})
        
        result = analyze_gcode_with_ai(gcode, controller, material, tool)
        return jsonify(result)
    except Exception as e:
        logger.warning(f"AI G-code analysis failed: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/ai/ask", methods=["POST"])
def ai_ask():
    """General AI assistant"""
    try:
        data = request.get_json()
        prompt = data.get("prompt", "")
        model = data.get("model")
        
        if not prompt:
            return jsonify({"success": False, "error": "No prompt provided"})
        
        result = ai_provider.call_ai(prompt, model)
        return jsonify(result)
    except Exception as e:
        logger.warning(f"AI ask failed: {e}")
        return jsonify({"success": False, "error": str(e)})

# ============================================================================
# MAIN ROUTES
# ============================================================================

@app.route("/")
def index():
    """Main page with fallback HTML"""
    try:
        ui_path = Path("ui/index.html")
        if ui_path.exists():
            with open(ui_path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception as e:
        logger.warning(f"Failed to read ui/index.html: {e}")
    
    fallback_html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CNCera - 3D Analysis & G-code Generation</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="/static/ncviewer/ncviewer.css">
        <style>
            #viewer { min-height: 400px; }
            #log, #glog { white-space: pre-wrap; }
            .tooltip { position: relative; }
            .tooltip:hover::after {
                content: attr(data-tooltip);
                position: absolute; z-index: 10; bottom: 100%; left: 50%; transform: translateX(-50%);
                background: #1f2937; color: #e5e7eb; padding: 4px 8px; border-radius: 4px;
                font-size: 0.875rem; white-space: nowrap;
            }
            .analysis-panel { 
                background: #f8fafc; color: #1f2937; 
                border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px;
            }
            .analysis-panel pre { 
                background: #ffffff; color: #374151; padding: 12px; 
                border-radius: 4px; border: 1px solid #d1d5db; font-family: 'Courier New', monospace;
            }
        </style>
    </head>
    <body class="bg-gray-900 text-gray-100 font-sans p-6">
        <div class="max-w-5xl mx-auto space-y-6">
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
                        <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Линейное отклонение для сетки (мм)">LinearDeflection</label>
                        <input id="linDef" type="number" step="0.01" value="0.1" min="0.01" max="10" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Угловое отклонение (градусы)">AngularDeflection (°)</label>
                        <input id="angDef" type="number" step="0.5" value="15" min="0.01" max="89" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Relative</label>
                        <input id="rel" type="checkbox" class="h-5 w-5 text-blue-600 bg-gray-700 border-gray-600 rounded">
                    </div>
                </div>
                <button onclick="analyze()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition">Анализировать</button>
                <div id="log" class="mt-4 text-gray-400"></div>
            </div>

            <!-- Analysis Results Section -->
            <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
                <h2 class="text-xl font-semibold mb-4">Результат анализа</h2>
                <div id="viewer" class="bg-gray-900 rounded-lg flex items-center justify-center"></div>
                <div id="meta" class="mt-4"></div>
                
                <!-- AI Analysis Panel -->
                <div id="ai-analysis" class="analysis-panel mt-4" style="display: none;">
                    <h3 class="text-lg font-medium mb-3">AI Анализ</h3>
                    <div id="ai-findings" class="mb-4"></div>
                    <div class="flex space-x-2">
                        <button onclick="aiInspectModel()" class="bg-green-600 text-white px-3 py-1 rounded text-sm hover:bg-green-700">AI: Inspect Model</button>
                        <button onclick="aiAnalyzeGcode()" class="bg-purple-600 text-white px-3 py-1 rounded text-sm hover:bg-purple-700">AI: Analyze G-code</button>
                    </div>
                </div>
                
                <p class="text-sm text-gray-500 mt-2">Офлайн-вьювер использует three.min.js, OrbitControls.js, STLLoader.js. Если они недоступны, отображается PNG.</p>
            </div>

            <!-- G-code Generation Section -->
            <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
                <h2 class="text-xl font-semibold mb-4">Генерация G-кода</h2>

                <!-- Controller and Operation Type Selection -->
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Контроллер</label>
                        <select id="controller" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                            <option value="fanuc_metric">Fanuc</option>
                            <option value="siemens">Siemens</option>
                            <option value="heidenhain">Heidenhain</option>
                            <option value="gsk">GSK</option>
                            <option value="mazak">Mazak</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Тип обработки</label>
                        <select id="operation_type" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100" onchange="toggleOperationSettings()">
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

                <!-- Tool Selection -->
                <div class="mb-6">
                    <h3 class="text-lg font-medium mb-3">Выбор инструмента</h3>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm text-gray-400 mb-1">Инструмент</label>
                            <select id="tool_select" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100" onchange="loadToolDefaults()">
                                <option value="">Выберите инструмент</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Диаметр инструмента (мм)">Ø инструмента, мм</label>
                            <input id="tool" type="number" value="3" step="0.1" min="0.1" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        </div>
                    </div>
                </div>

                <!-- Tool Parameters -->
                <div class="mb-6">
                    <h3 class="text-lg font-medium mb-3">Параметры инструмента</h3>
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        <div>
                            <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Скорость шпинделя (об/мин)">Spindle, об/мин</label>
                            <input id="spindle" type="number" value="8000" step="100" min="1000" max="24000" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        </div>
                        <div>
                            <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Общая подача (мм/мин)">Feed, мм/мин</label>
                            <input id="feed" type="number" value="300" step="10" min="10" max="5000" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        </div>
                        <div>
                            <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Скорость погружения (мм/мин)">Plunge, мм/мин</label>
                            <input id="plunge" type="number" value="120" step="10" min="10" max="2000" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        </div>
                        <div>
                            <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Безопасная высота по Z (мм)">Clearance Z, мм</label>
                            <input id="clearance" type="number" value="5" step="0.5" min="1" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        </div>
                    </div>
                </div>

                <!-- Milling Specific Settings -->
                <div id="milling_settings" class="mb-6">
                    <h3 class="text-lg font-medium mb-3">Настройки фрезерования</h3>
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        <div>
                            <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Доля диаметра инструмента (0.05—0.95)">Степовер</label>
                            <input id="stepover" type="number" value="0.4" step="0.05" min="0.05" max="0.95" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        </div>
                        <div>
                            <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Шаг по Z для черновой обработки">Stepdown Z, мм</label>
                            <input id="stepdown" type="number" value="0" step="0.5" min="0" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        </div>
                        <div>
                            <label class="block text-sm text-gray-400 mb-1">Ось проходов</label>
                            <select id="dir" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                                <option>X</option>
                                <option>Y</option>
                            </select>
                        </div>
                    </div>

                    <!-- Advanced Milling Options -->
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
                        <div>
                            <label class="block text-sm text-gray-400 mb-1">Waterline</label>
                            <input id="waterline" type="checkbox" class="h-5 w-5 text-blue-600 bg-gray-700 border-gray-600 rounded">
                        </div>
                        <div>
                            <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Шаг по Z для waterline">Шаг Waterline dZ, мм</label>
                            <input id="waterline_dz" type="number" value="0.5" step="0.1" min="0" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        </div>
                        <div>
                            <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Степовер для финишной обработки">Finish stepover</label>
                            <input id="finish_stepover" type="number" value="0.3" step="0.05" min="0.05" max="0.95" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        </div>
                    </div>
                </div>

                <!-- Allowance Settings -->
                <div class="mb-6">
                    <h3 class="text-lg font-medium mb-3">Ручные припуски</h3>
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        <div>
                            <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Припуск по оси X">Припуск X, мм</label>
                            <input id="allowance_x" type="number" value="0" step="0.1" min="-10" max="10" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        </div>
                        <div>
                            <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Припуск по оси Y">Припуск Y, мм</label>
                            <input id="allowance_y" type="number" value="0" step="0.1" min="-10" max="10" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        </div>
                        <div>
                            <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Припуск по оси Z">Припуск Z, мм</label>
                            <input id="allowance_z" type="number" value="0" step="0.1" min="-10" max="10" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        </div>
                    </div>
                </div>

                <div class="flex items-center space-x-4">
                    <button onclick="gen()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition">Сгенерировать G-код</button>
                    <span id="glog" class="text-gray-400"></span>
                </div>
            </div>

            <!-- G-code Preview Section -->
            <div id="gcode-preview" class="bg-gray-800 p-6 rounded-lg shadow-lg" style="display: none;">
                <h2 class="text-xl font-semibold mb-4">Предпросмотр G-кода</h2>
                <div id="ncviewer" class="ncviewer-container"></div>
                <div id="gcode-content" class="mt-4"></div>
            </div>
        </div>

        <script src="/static/js/app.js"></script>
        <script src="/static/js/ncviewer.js"></script>
    </body>
    </html>
    """
    return fallback_html

@app.route("/favicon.ico")
def favicon():
    return "", 204

@app.route("/static/<path:filename>")
def serve_static(filename: str):
    """Serve static files with fallback for Windows/OneDrive paths"""
    try:
        return send_from_directory(str(STATIC), filename)
    except Exception as e:
        # Try fallback with BASE path
        try:
            static_dir = BASE / "static"
            return send_from_directory(str(static_dir), filename)
        except Exception as e2:
            logger.warning("Static file not found: %s - %s", filename, str(e2))
            return f"Static file not found: {filename}", 404

@app.route("/models/<path:filename>")
def serve_models(filename: str):
    ext = Path(filename).suffix.lower()
    mime = {"stl": "model/stl", "png": "image/png"}.get(ext[1:], "application/octet-stream")
    return send_from_directory(str(MODELS), filename, mimetype=mime)

@app.route("/download_results")
def download_results():
    filename = request.args.get("filename", "")
    if not secure_filename_check(filename):
        return jsonify({"success": False, "error": "Invalid filename"}), 400
    path = TEMP / filename
    if not filename or not path.exists():
        return jsonify({"success": False, "error": "File not found"}), 404
    return send_file(str(path), as_attachment=True, mimetype="application/json", download_name=filename)

@app.route("/upload", methods=["POST"])
def upload():
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
        result_name = f"result_{hashlib.md5(str(disk_path).encode()).hexdigest()}.json"
        (TEMP / result_name).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        res["result_filename"] = result_name

        png_abs = MODELS / (Path(stl_name).with_suffix(".png").name)
        preview_available = False
        if not png_abs.exists():
            preview_available = render_stl_to_png(stl_abs, png_abs)
        else:
            preview_available = True
            
        if preview_available:
            res["preview_png"] = f"/models/{png_abs.name}"
            try:
                res["preview_png_data"] = "data:image/png;base64," + base64.b64encode(png_abs.read_bytes()).decode("ascii")
            except Exception as e:
                logger.warning(f"PNG base64 embed failed: {e}")
        
        res["preview_available"] = preview_available
        return jsonify(res)
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

@app.route("/generate_gcode", methods=["POST"])
def generate_gcode_route():
    try:
        data = request.get_json(force=True, silent=True) or {}
        is_valid, error_msg = validate_api_params(data)
        if not is_valid:
            return jsonify({"success": False, "error": error_msg})
        
        model_path = data.get("model_path")
        if not model_path or not model_path.startswith("/models/"):
            return jsonify({"success": False, "error": "Некорректный model_path"})
        stl_abs = MODELS / Path(model_path).name
        if not stl_abs.exists():
            return jsonify({"success": False, "error": "STL не найден"})

        controller = data.get("controller", "fanuc_metric")
        operation_type = data.get("operation_type", "milling")

        allowance_x = validate_float(data.get("allowance_x", 0.0), 0.0, -10.0, 10.0)
        allowance_y = validate_float(data.get("allowance_y", 0.0), 0.0, -10.0, 10.0)
        allowance_z = validate_float(data.get("allowance_z", 0.0), 0.0, -10.0, 10.0)

        if operation_type in ("milling", "roughing", "finishing", "chamfer"):
            params = {
                "tool_diam": validate_float(data.get("tool", 3.0), 3.0, 0.1, 50.0),
                "stepover": validate_float(data.get("stepover", 0.4), 0.4, 0.05, 0.95),
                "feed": validate_float(data.get("feed", 300.0), 300.0, 10.0, 5000.0),
                "plunge": validate_float(data.get("plunge", 120.0), 120.0, 10.0, 2000.0),
                "clearance": validate_float(data.get("clearance", 5.0), 5.0, 1.0, 50.0),
                "spindle": validate_int(data.get("spindle", 8000), 8000, 1000, 24000) if data.get("spindle") else None,
                "dir_axis": str(data.get("dir", "X")).upper(),
                "origin": str(data.get("origin", "bbox_min")),
                "stepdown": validate_float(data.get("stepdown", 0.0), 0.0, 0.0, 50.0),
                "waterline": bool(data.get("waterline", False)),
                "waterline_dz": validate_float(data.get("waterline_dz", 0.0), 0.0, 0.0, 50.0),
                "finish_stepover": validate_float(data.get("finish_stepover", 0.0), 0.4, 0.05, 0.95) or None,
                "allowance_x": allowance_x, "allowance_y": allowance_y, "allowance_z": allowance_z,
                "controller": controller, "operation_type": operation_type
            }

            gname = f"gcode_{controller}_{operation_type}_{Path(stl_abs).stem}.nc"
            gout = TEMP / gname
            meta = generate_raster_gcode(stl_abs, gout, **params)
        else:
            return jsonify({"success": False, "error": "Неподдерживаемый тип операции"})

        with open(gout, "r", encoding="utf-8") as f:
            gcode_content = f.read()
        validation_result = validate_gcode(gcode_content, controller)

        png_abs = MODELS / (Path(model_path).name.replace('.stl', '.png'))
        preview_available = png_abs.exists()

        return jsonify({
            "success": True, "gcode_path": f"/download_gcode?name={gname}",
            "gcode_content": gcode_content, "grid": meta.get("grid", {}),
            "origin": meta.get("origin", {}), "controller": controller,
            "operation": operation_type, "validation": validation_result,
            "preview_available": preview_available
        })
    except Exception as e:
        logger.error("G-code generation failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)})

@app.route("/download_gcode")
def download_gcode():
    name = request.args.get("name", "")
    if not secure_filename_check(name):
        return jsonify({"success": False, "error": "Invalid filename"}), 400
    path = TEMP / name
    if not name or not path.exists():
        return jsonify({"success": False, "error": "File not found"}), 404
    return send_file(str(path), as_attachment=True, download_name=name, mimetype="text/plain")

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    # Startup diagnostics
    logger.info("Starting CNCera server...")
    logger.info("BASE path: %s", BASE)
    logger.info("Static folder: %s", app.static_folder)
    logger.info("Static URL path: %s", app.static_url_path)
    
    # Check required static files
    required_assets = [
        "static/js/app.js",
        "static/js/ncviewer.js"
    ]
    
    for asset in required_assets:
        asset_path = BASE / asset
        if asset_path.exists():
            logger.info("✓ Found: %s", asset)
        else:
            logger.warning("✗ Missing: %s", asset)
    
    # Check if UI template references static assets correctly
    try:
        ui_path = Path("ui/index.html")
        if ui_path.exists():
            ui_content = ui_path.read_text(encoding="utf-8")
            script_tags = []
            for line in ui_content.split('\n'):
                if 'src=' in line and 'static' in line:
                    script_tags.append(line.strip())
            if script_tags:
                logger.info("Found script tags in UI: %s", script_tags)
    except Exception as e:
        logger.warning("Could not check UI template: %s", e)
    
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)