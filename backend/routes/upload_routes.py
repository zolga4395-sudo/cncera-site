"""
Маршруты для загрузки и обработки файлов
"""

import json
import shutil
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from utils.validators import allowed_file, validate_float
from utils.file_utils import get_uploaded_size, generate_file_hash, cleanup_temp_files
from services.freecad_service import FreecadService
from services.stl_service import StlService

upload_bp = Blueprint('upload', __name__)

@upload_bp.route('/upload', methods=['POST'])
def upload_file():
    """Загрузка и обработка 3D файлов"""
    disk_path = None
    
    try:
        # Проверка наличия файла
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "Файл не предоставлен"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "Файл не выбран"}), 400
        
        # Проверка расширения
        if not allowed_file(file.filename, current_app.config['ALLOWED_EXTENSIONS']):
            return jsonify({
                "success": False, 
                "error": "Поддерживаются только форматы: .step, .stp, .stl"
            }), 400
        
        # Проверка размера
        file_size = get_uploaded_size(file)
        max_size = current_app.config['MAX_CONTENT_LENGTH']
        if max_size and file_size > max_size:
            return jsonify({
                "success": False, 
                "error": f"Файл слишком большой (макс. {max_size // (1024*1024)} МБ)"
            }), 400
        
        # Сохранение файла
        filename = secure_filename(file.filename)
        disk_path = current_app.config['TEMP_FOLDER'] / filename
        file.save(str(disk_path))
        
        # Получение параметров обработки
        units = request.form.get('units', 'auto').lower()
        linear_deflection = validate_float(request.form.get('linear_deflection', 0.1), 0.1, 0.01, 10.0)
        angular_deflection = validate_float(request.form.get('angular_deflection_deg', 15), 15.0, 0.01, 89.0)
        relative = request.form.get('relative', 'false').lower() in ('1', 'true', 'yes', 'on')
        
        # Обработка файла
        ext = disk_path.suffix.lower()
        stl_name = generate_file_hash(disk_path) + '.stl'
        stl_path = current_app.config['MODELS_FOLDER'] / stl_name
        
        if ext in ('.step', '.stp'):
            # Конвертация STEP в STL
            freecad_service = FreecadService(current_app.config)
            result = freecad_service.convert_step_to_stl(
                disk_path, stl_path, linear_deflection, angular_deflection, relative, units
            )
        elif ext == '.stl':
            # Копирование STL файла
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
        
        # Анализ STL
        stl_service = StlService()
        mesh_info = stl_service.analyze_stl(stl_path)
        result['mesh_info'] = mesh_info
        
        # Генерация превью
        png_path = current_app.config['MODELS_FOLDER'] / (stl_name.replace('.stl', '.png'))
        stl_service.render_stl_to_png(stl_path, png_path)
        
        # Подготовка ответа
        result.update({
            "model_path": f"/api/models/{stl_name}",
            "preview_png": f"/api/models/{png_path.name}" if png_path.exists() else None
        })
        
        # Сохранение результата
        result_name = f"result_{generate_file_hash(disk_path)}.json"
        result_path = current_app.config['TEMP_FOLDER'] / result_name
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        result['result_filename'] = result_name
        
        current_app.logger.info(f"File processed successfully: {filename}")
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Upload failed: {e}", exc_info=True)
        return jsonify({
            "success": False, 
            "error": f"Ошибка обработки файла: {str(e)}"
        }), 500
        
    finally:
        # Очистка временных файлов
        cleanup_temp_files(disk_path)

@upload_bp.route('/upload/status/<task_id>')
def upload_status(task_id):
    """Проверка статуса обработки файла (для будущего асинхронного режима)"""
    return jsonify({
        "task_id": task_id,
        "status": "completed",  # В текущей версии все синхронно
        "progress": 100
    })