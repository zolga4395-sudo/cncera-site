# ---- Routes for Enhanced CNCera App ----

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
        # Collect current system metrics
        current_metrics = metrics_collector.collect_system_metrics()
        
        # Check system health
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "system_metrics": asdict(current_metrics) if current_metrics else None,
            "uptime_seconds": (datetime.now() - metrics_collector.start_time).total_seconds()
        }
        
        # Check for issues
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
            "error": error.user_message,
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route("/upload", methods=["POST"])
def upload():
    disk_path = None
    start_time = time.time()
    
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "Нет файла"})
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "Не выбран файл"})
        
        # Enhanced security validation
        if not allowed_file(file.filename):
            return jsonify({"success": False, "error": "Неподдерживаемый формат файла или небезопасное имя файла"})
        
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

        # Record successful processing
        processing_time = time.time() - start_time
        metrics_collector.record_processing("file_upload", sz, processing_time, True)

        return jsonify(res)
        
    except FileNotFoundError as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "File upload")
        metrics_collector.record_processing("file_upload", 0, processing_time, False, error.error_type.value)
        return jsonify({"success": False, "error": str(e)})
    except subprocess.TimeoutExpired:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(subprocess.TimeoutExpired("FreeCAD timeout"), "File upload")
        metrics_collector.record_processing("file_upload", 0, processing_time, False, error.error_type.value)
        return jsonify({"success": False, "error": "Таймаут запуска FreeCADCmd"})
    except Exception as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "File upload")
        metrics_collector.record_processing("file_upload", 0, processing_time, False, error.error_type.value)
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
    start_time = time.time()
    
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

        # Enhanced parameter validation
        validated_params = SecurityValidator.validate_gcode_params(data)
        
        allowance_x = validate_float(data.get("allowance_x", 0.0), 0.0, -10.0, 10.0)
        allowance_y = validate_float(data.get("allowance_y", 0.0), 0.0, -10.0, 10.0)
        allowance_z = validate_float(data.get("allowance_z", 0.0), 0.0, -10.0, 10.0)

        if operation_type in ("milling", "roughing", "finishing", "chamfer"):
            params = {
                "tool_diam": validated_params.get("tool_diam", 3.0),
                "stepover": validated_params.get("stepover", 0.4),
                "feed": validated_params.get("feed", 300.0),
                "plunge": validated_params.get("plunge", 120.0),
                "clearance": validated_params.get("clearance", 5.0),
                "spindle": validated_params.get("spindle", 8000) if data.get("spindle") else None,
                "dir_axis": str(data.get("dir", "X")).upper(),
                "origin": str(data.get("origin", "bbox_min")),
                "stepdown": validated_params.get("stepdown", 0.0),
                "waterline": bool(data.get("waterline", False)),
                "waterline_dz": validate_float(data.get("waterline_dz", 0.0), 0.0, 0.0, 50.0),
                "finish_stepover": validate_float(data.get("finish_stepover", 0.0), 0.4, 0.05, 0.95) or None,
                "allowance_x": allowance_x,
                "allowance_y": allowance_y,
                "allowance_z": allowance_z,
                "controller": controller,
                "operation_type": operation_type,
                "material_grade": data.get("material_grade", "42CrMo4"),
                "flutes": validate_int(data.get("flutes", 2), 2, 1, 8),
                "corner_radius": validate_float(data.get("corner_radius", 0.0), 0.0, 0.0, 5.0)
            }

            gname = f"gcode_{controller}_{operation_type}_{Path(stl_abs).stem}.nc"
            gout = TEMP / gname

            if operation_type == "chamfer":
                meta = generate_chamfer_gcode(stl_abs, gout, **params)
            else:
                # Use enhanced milling generation
                meta = generate_enhanced_milling_gcode(stl_abs, gout, **params)

        elif operation_type == "turning":
            params = {
                "tool_diam": validated_params.get("tool_diam", 3.0),
                "workpiece_diameter": validate_float(data.get("workpiece_diameter", 50.0), 50.0, 1.0, 500.0),
                "cut_depth": validate_float(data.get("cut_depth", 1.0), 1.0, 0.1, 10.0),
                "feed": validated_params.get("feed", 300.0),
                "feed_per_rev": validate_float(data.get("feed_per_rev", 0.2), 0.2, 0.01, 2.0),
                "spindle": validated_params.get("spindle", 1000),
                "clearance": validated_params.get("clearance", 5.0),
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
                "feed": validated_params.get("feed", 300.0),
                "spindle": validated_params.get("spindle", 8000),
                "clearance": validated_params.get("clearance", 5.0),
                "drill_cycle": str(data.get("drill_cycle", "G81")),
                "peck_depth": validate_float(data.get("peck_depth", 2.0), 2.0, 0.1, 10.0),
                "controller": controller
            }

            gname = f"gcode_{controller}_drilling_{Path(stl_abs).stem}.nc"
            gout = TEMP / gname
            meta = generate_drilling_gcode(stl_abs, gout, **params)
        else:
            return jsonify({"success": False, "error": "Неподдерживаемый тип операции"})

        # Record successful G-code generation
        processing_time = time.time() - start_time
        metrics_collector.record_processing(f"gcode_{operation_type}", stl_abs.stat().st_size, processing_time, True)

        return jsonify({
            "success": True,
            "gcode_path": f"/download_gcode?name={gname}",
            "grid": meta.get("grid", {}),
            "origin": meta.get("origin", {}),
            "controller": controller,
            "operation": operation_type,
            "cutting_params": meta.get("cutting_params", {}),
            "material": meta.get("material", {}),
            "tool": meta.get("tool", {}),
            "processing_time": processing_time
        })
        
    except Exception as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "G-code generation")
        metrics_collector.record_processing(
            f"gcode_{data.get('operation_type', 'unknown')}", 
            0, 
            processing_time, 
            False, 
            error.error_type.value
        )
        logger.error("G-code generation failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)})

@app.route("/download_gcode")
def download_gcode():
    name = request.args.get("name", "")
    path = TEMP / name
    if not name or not path.exists():
        return "Файл не найден", 404
    return send_file(str(path), as_attachment=True, download_name=name, mimetype="text/plain")

@app.route("/gcode_preview")
def gcode_preview():
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "Parameter 'name' is required"}), 400
    safe_name = Path(name).name  # prevent path traversal
    path = TEMP / safe_name
    if not path.exists() or not path.is_file():
        return jsonify({"success": False, "error": "G-code file not found"}), 404
    try:
        lines = []
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for i, line in enumerate(fh):
                if i >= 40:
                    break
                lines.append(line.rstrip("\n\r"))
        return jsonify({"success": True, "name": safe_name, "lines": lines})
    except Exception as e:
        return jsonify({"success": False, "error": f"Read error: {e}"}), 500

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        provider = (data.get("provider") or "").strip().lower()
        model = (data.get("model") or "").strip()
        message = (data.get("message") or "").strip()
        if not provider or not message:
            return jsonify({"success": False, "error": "Provide 'provider' and 'message'"}), 400

        # Defaults
        if provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                return jsonify({"success": False, "error": "OPENAI_API_KEY not set"}), 400
            if not model:
                model = "gpt-4o-mini"
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": message}],
                "temperature": float(data.get("temperature", 0.2)),
            }
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            if r.status_code >= 400:
                return jsonify({"success": False, "error": f"OpenAI: {r.status_code} {r.text[:300]}"}), 400
            j = r.json()
            text = (j.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()

        elif provider in ("anthropic", "claude"):
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                return jsonify({"success": False, "error": "ANTHROPIC_API_KEY not set"}), 400
            if not model:
                model = "claude-3-5-haiku-latest"
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": api_key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
            }
            payload = {
                "model": model,
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": message}],
            }
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            if r.status_code >= 400:
                return jsonify({"success": False, "error": f"Anthropic: {r.status_code} {r.text[:300]}"}), 400
            j = r.json()
            blocks = j.get("content") or []
            text_parts = []
            for b in blocks:
                if isinstance(b, dict) and b.get("type") == "text":
                    text_parts.append(b.get("text", ""))
            text = "\n".join(tp for tp in text_parts if tp).strip()

        elif provider in ("grok", "xai", "x-ai", "x_ai"):
            api_key = os.environ.get("XAI_API_KEY", "")
            if not api_key:
                return jsonify({"success": False, "error": "XAI_API_KEY not set"}), 400
            if not model:
                model = "grok-2-latest"
            url = "https://api.x.ai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": message}],
                "temperature": float(data.get("temperature", 0.2)),
            }
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            if r.status_code >= 400:
                return jsonify({"success": False, "error": f"xAI: {r.status_code} {r.text[:300]}"}), 400
            j = r.json()
            text = (j.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
        else:
            return jsonify({"success": False, "error": "Unsupported provider. Use: openai, anthropic, grok"}), 400

        return jsonify({"success": True, "provider": provider, "model": model, "reply": text})
    except Exception as e:
        return jsonify({"success": False, "error": f"Chat error: {e}"}), 500

if __name__ == "__main__":
    logger.info("Starting Enhanced CNCera server...")
    
    # Start monitoring
    try:
        import threading
        def start_monitoring():
            metrics_collector.collect_system_metrics()
            threading.Timer(30.0, start_monitoring).start()
        start_monitoring()
        logger.info("System monitoring started")
    except Exception as e:
        logger.warning(f"Failed to start monitoring: {e}")
    
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)