# ---- AI Routes ----
@app.route("/ai_chat", methods=["POST"])
def ai_chat_route():
    """Handle AI chat requests"""
    try:
        data = request.get_json() or {}
        message = data.get("message", "")
        session_id = data.get("session_id", "default")
        context = data.get("context")
        
        if not message.strip():
            return jsonify({"success": False, "error": "Empty message"})
        
        response = chat_with_ai(message, session_id, context)
        
        return jsonify({
            "success": True,
            "response": response,
            "session_id": session_id
        })
        
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/ai_analyze", methods=["POST"])
def ai_analyze_route():
    """Analyze part using AI"""
    try:
        data = request.get_json() or {}
        model_path = data.get("model_path")
        
        if not model_path or not model_path.startswith("/models/"):
            return jsonify({"success": False, "error": "Invalid model path"})
        
        stl_abs = MODELS / Path(model_path).name
        if not stl_abs.exists():
            return jsonify({"success": False, "error": "STL file not found"})
        
        # Get part info from the stored results
        result_files = list(TEMP.glob("result_*.json"))
        part_info = {}
        
        for result_file in result_files:
            try:
                result_data = json.loads(result_file.read_text())
                if result_data.get("model_path") == model_path:
                    part_info = result_data
                    break
            except:
                continue
        
        if not part_info:
            # Basic analysis if no stored data
            part_info = {
                "geometry": {"dimensions": {"length": 0, "width": 0, "height": 0}},
                "mesh_info": analyze_stl(stl_abs)
            }
        
        ai_analysis = analyze_part_with_ai(stl_abs, part_info)
        
        return jsonify({
            "success": True,
            "analysis": ai_analysis,
            "part_info": part_info
        })
        
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/ai_generate_gcode", methods=["POST"])
def ai_generate_gcode_route():
    """Generate G-code parameters using AI"""
    try:
        data = request.get_json() or {}
        model_path = data.get("model_path")
        requirements = data.get("requirements", "")
        
        if not model_path or not model_path.startswith("/models/"):
            return jsonify({"success": False, "error": "Invalid model path"})
        
        stl_abs = MODELS / Path(model_path).name
        if not stl_abs.exists():
            return jsonify({"success": False, "error": "STL file not found"})
        
        # Get part info
        result_files = list(TEMP.glob("result_*.json"))
        part_info = {}
        
        for result_file in result_files:
            try:
                result_data = json.loads(result_file.read_text())
                if result_data.get("model_path") == model_path:
                    part_info = result_data
                    break
            except:
                continue
        
        if not part_info:
            part_info = {
                "geometry": {"dimensions": {"length": 0, "width": 0, "height": 0}},
                "mesh_info": analyze_stl(stl_abs)
            }
        
        ai_params = generate_gcode_with_ai(stl_abs, part_info, requirements)
        
        return jsonify({
            "success": True,
            "parameters": ai_params
        })
        
    except Exception as e:
        logger.error(f"AI G-code generation error: {e}")
        return jsonify({"success": False, "error": str(e)})

# ---- Basic Routes ----
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

@app.route("/download_gcode")
def download_gcode():
    name = request.args.get("name", "")
    path = TEMP / name
    if not name or not path.exists():
        return "Файл не найден", 404
    return send_file(str(path), as_attachment=True, download_name=name, mimetype="text/plain")