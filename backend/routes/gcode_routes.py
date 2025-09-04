"""
Маршруты для генерации G-кода
"""

from pathlib import Path
from flask import Blueprint, request, jsonify, current_app

from utils.validators import validate_gcode_params
from services.gcode_service import GcodeService

gcode_bp = Blueprint('gcode', __name__)

@gcode_bp.route('/gcode/generate', methods=['POST'])
def generate_gcode():
    """Генерация G-кода"""
    try:
        data = request.get_json() or {}
        model_path = data.get('model_path', '')
        
        if not model_path or not model_path.startswith('/api/models/'):
            return jsonify({"success": False, "error": "Некорректный путь к модели"}), 400
        
        # Проверяем существование STL файла
        model_filename = Path(model_path).name
        stl_path = current_app.config['MODELS_FOLDER'] / model_filename
        
        if not stl_path.exists():
            return jsonify({"success": False, "error": "STL файл не найден"}), 404
        
        # Валидация параметров
        params = validate_gcode_params(data)
        
        # Создаем сервис генерации G-кода
        gcode_service = GcodeService(current_app.config)
        
        # Генерируем имя выходного файла
        controller = params['controller']
        operation = params['operation_type']
        gcode_filename = f"gcode_{controller}_{operation}_{stl_path.stem}.nc"
        gcode_path = current_app.config['TEMP_FOLDER'] / gcode_filename
        
        # Генерируем G-код
        result = gcode_service.generate_gcode(stl_path, gcode_path, **params)
        
        return jsonify({
            "success": True,
            "gcode_filename": gcode_filename,
            "download_url": f"/api/files/gcode/{gcode_filename}",
            "metadata": result,
            "controller": controller,
            "operation": operation
        })
        
    except Exception as e:
        current_app.logger.error(f"G-code generation failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@gcode_bp.route('/gcode/preview', methods=['POST'])
def preview_gcode():
    """Предпросмотр G-кода (первые несколько строк)"""
    try:
        data = request.get_json() or {}
        gcode_filename = data.get('gcode_filename', '')
        
        if not gcode_filename:
            return jsonify({"success": False, "error": "Не указан файл G-кода"}), 400
        
        gcode_path = current_app.config['TEMP_FOLDER'] / gcode_filename
        
        if not gcode_path.exists():
            return jsonify({"success": False, "error": "G-код файл не найден"}), 404
        
        # Читаем первые 50 строк для предпросмотра
        lines = []
        with open(gcode_path, 'r', encoding='ascii', errors='ignore') as f:
            for i, line in enumerate(f):
                if i >= 50:
                    break
                lines.append(line.strip())
        
        return jsonify({
            "success": True,
            "preview": lines,
            "total_lines": i + 1,
            "truncated": i >= 49
        })
        
    except Exception as e:
        current_app.logger.error(f"G-code preview failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@gcode_bp.route('/gcode/validate', methods=['POST'])
def validate_gcode():
    """Валидация параметров G-кода (без генерации)"""
    try:
        data = request.get_json() or {}
        
        # Валидируем параметры
        validated_params = validate_gcode_params(data)
        
        # Проверяем обязательные поля
        required_fields = ['tool_diam', 'feed', 'controller', 'operation_type']
        missing_fields = [field for field in required_fields if not validated_params.get(field)]
        
        if missing_fields:
            return jsonify({
                "success": False,
                "error": f"Отсутствуют обязательные поля: {', '.join(missing_fields)}"
            }), 400
        
        return jsonify({
            "success": True,
            "validated_params": validated_params,
            "estimated_time": _estimate_machining_time(validated_params)
        })
        
    except Exception as e:
        current_app.logger.error(f"G-code validation failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

def _estimate_machining_time(params: dict) -> str:
    """Примерная оценка времени обработки"""
    # Упрощенная оценка на основе параметров
    tool_diam = params.get('tool_diam', 3.0)
    feed = params.get('feed', 300.0)
    operation = params.get('operation_type', 'milling')
    
    # Базовое время в зависимости от операции
    base_time = {
        'roughing': 30,
        'finishing': 15,
        'milling': 20,
        'chamfer': 5
    }.get(operation, 20)
    
    # Корректировка на основе параметров
    time_factor = (tool_diam / 3.0) * (300.0 / feed)
    estimated_minutes = int(base_time * time_factor)
    
    if estimated_minutes < 60:
        return f"{estimated_minutes} минут"
    else:
        hours = estimated_minutes // 60
        minutes = estimated_minutes % 60
        return f"{hours}ч {minutes}мин"