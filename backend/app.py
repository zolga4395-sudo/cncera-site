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
BASE = Path(__file__).parent.parent.resolve()
TEMP = BASE / "temp"
TEMP.mkdir(exist_ok=True)
MODELS = BASE / "models"
MODELS.mkdir(exist_ok=True)
STATIC = BASE / "static"
STATIC.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".step", ".stp", ".stl"}
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB limit

# ---- Global error handler ----
@app.errorhandler(Exception)
def handle_error(e):
    logger.error("Uncaught exception: %s", e, exc_info=True)
    if request.path in ("/upload", "/generate_gcode"):
        return jsonify({"success": False, "error": f"Critical error: {e.__class__.__name__}: {str(e)}"}), 200
    return "Internal Server Error", 500

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

# Import G-code generation functions
from gcode_generator import (
    prepare_bins, point_in_tri_xy, z_for, build_top_sampler,
    marching_squares, get_controller_settings,
    generate_chamfer_gcode, generate_turning_gcode, generate_drilling_gcode,
    generate_raster_gcode
)

# ---- Routes ----
@app.route("/")
def index():
    return send_file(str(BASE / "frontend" / "index.html"))

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
        if not png_abs.exists():
            render_stl_to_png(stl_abs, png_abs)
        if png_abs.exists():
            res["preview_png"] = f"/models/{png_abs.name}"
            try:
                res["preview_png_data"] = "data:image/png;base64," + base64.b64encode(png_abs.read_bytes()).decode("ascii")
            except Exception as e:
                logger.warning(f"PNG base64 embed failed: {e}")

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
        model_path = data.get("model_path")
        if not model_path or not model_path.startswith("/models/"):
            return jsonify({"success": False, "error": "Некорректный model_path"})
        stl_abs = MODELS / Path(model_path).name
        if not stl_abs.exists():
            return jsonify({"success": False, "error": "STL не найден"})

        controller = data.get("controller", "fanuc")
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
                "allowance_x": allowance_x,
                "allowance_y": allowance_y,
                "allowance_z": allowance_z,
                "controller": controller,
                "operation_type": operation_type
            }

            gname = f"gcode_{controller}_{operation_type}_{Path(stl_abs).stem}.nc"
            gout = TEMP / gname

            if operation_type == "chamfer":
                meta = generate_chamfer_gcode(stl_abs, gout, **params)
            else:
                meta = generate_raster_gcode(stl_abs, gout, **params)

        elif operation_type == "turning":
            params = {
                "tool_diam": validate_float(data.get("tool", 3.0), 3.0, 0.1, 50.0),
                "workpiece_diameter": validate_float(data.get("workpiece_diameter", 50.0), 50.0, 1.0, 500.0),
                "cut_depth": validate_float(data.get("cut_depth", 1.0), 1.0, 0.1, 10.0),
                "feed": validate_float(data.get("feed", 300.0), 300.0, 10.0, 5000.0),
                "feed_per_rev": validate_float(data.get("feed_per_rev", 0.2), 0.2, 0.01, 2.0),
                "spindle": validate_int(data.get("spindle", 1000), 1000, 100, 5000),
                "clearance": validate_float(data.get("clearance", 5.0), 5.0, 1.0, 50.0),
                "turning_type": str(data.get("turning_type", "roughing")),
                "controller": controller
            }

            gname = f"gcode_{controller}_turning_{Path(stl_abs).stem}.nc"
            gout = TEMP / gname
            meta = generate_turning_gcode(stl_abs, gout, **params)

        elif operation_type == "drilling":
            params = {
                "drill_diameter": validate_float(data.get("drill_diameter", 6.0), 6.0, 0.5, 50.0),
                "drill_depth": validate_float(data.get("drill_depth", 10.0), 10.0, 1.0, 100.0),
                "feed": validate_float(data.get("feed", 300.0), 300.0, 10.0, 5000.0),
                "spindle": validate_int(data.get("spindle", 8000), 8000, 1000, 24000),
                "clearance": validate_float(data.get("clearance", 5.0), 5.0, 1.0, 50.0),
                "drill_cycle": str(data.get("drill_cycle", "G81")),
                "peck_depth": validate_float(data.get("peck_depth", 2.0), 2.0, 0.1, 10.0),
                "controller": controller
            }

            gname = f"gcode_{controller}_drilling_{Path(stl_abs).stem}.nc"
            gout = TEMP / gname
            meta = generate_drilling_gcode(stl_abs, gout, **params)
        else:
            return jsonify({"success": False, "error": "Неподдерживаемый тип операции"})

        return jsonify({
            "success": True,
            "gcode_path": f"/download_gcode?name={gname}",
            "grid": meta.get("grid", {}),
            "origin": meta.get("origin", {}),
            "controller": controller,
            "operation": operation_type
        })
    except Exception as e:
        logger.error("G-code generation failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)})

@app.route("/download_gcode")
def download_gcode():
    name = request.args.get("name", "")
    path = TEMP / name
    if not name or not path.exists():
        return "Файл не найден", 404
    return send_file(str(path), as_attachment=True, download_name=name, mimetype="text/plain")

if __name__ == "__main__":
    logger.info("Starting CNCera server...")
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)