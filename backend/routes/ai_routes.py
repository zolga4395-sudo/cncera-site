"""
Маршруты для ИИ функциональности
"""

import json
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app

from services.ai_service import AiService
from services.stl_service import StlService

ai_bp = Blueprint('ai', __name__)

@ai_bp.route('/ai/chat', methods=['POST'])
def ai_chat():
    """ИИ чат-консультант"""
    try:
        data = request.get_json() or {}
        message = data.get('message', '').strip()
        session_id = data.get('session_id', 'default')
        context = data.get('context')
        
        if not message:
            return jsonify({"success": False, "error": "Сообщение не может быть пустым"}), 400
        
        ai_service = AiService(current_app.config)
        
        if not ai_service.is_available():
            return jsonify({
                "success": False, 
                "error": "ИИ сервис недоступен. Проверьте настройку OPENAI_API_KEY"
            }), 503
        
        response = ai_service.chat(message, session_id, context)
        
        return jsonify({
            "success": True,
            "response": response,
            "session_id": session_id
        })
        
    except Exception as e:
        current_app.logger.error(f"AI chat error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@ai_bp.route('/ai/analyze', methods=['POST'])
def ai_analyze():
    """ИИ анализ детали"""
    try:
        data = request.get_json() or {}
        model_path = data.get('model_path', '')
        
        if not model_path or not model_path.startswith('/api/models/'):
            return jsonify({"success": False, "error": "Некорректный путь к модели"}), 400
        
        # Извлекаем имя файла из пути
        model_filename = Path(model_path).name
        stl_path = current_app.config['MODELS_FOLDER'] / model_filename
        
        if not stl_path.exists():
            return jsonify({"success": False, "error": "STL файл не найден"}), 404
        
        ai_service = AiService(current_app.config)
        
        if not ai_service.is_available():
            return jsonify({
                "success": False, 
                "error": "ИИ сервис недоступен. Проверьте настройку OPENAI_API_KEY"
            }), 503
        
        # Получаем информацию о детали
        part_info = _get_part_info(model_path)
        
        # Анализируем с помощью ИИ
        analysis = ai_service.analyze_part(stl_path, part_info)
        
        return jsonify({
            "success": True,
            "analysis": analysis,
            "part_info": part_info
        })
        
    except Exception as e:
        current_app.logger.error(f"AI analysis error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@ai_bp.route('/ai/generate-params', methods=['POST'])
def ai_generate_params():
    """ИИ генерация параметров G-кода"""
    try:
        data = request.get_json() or {}
        model_path = data.get('model_path', '')
        requirements = data.get('requirements', '')
        
        if not model_path or not model_path.startswith('/api/models/'):
            return jsonify({"success": False, "error": "Некорректный путь к модели"}), 400
        
        model_filename = Path(model_path).name
        stl_path = current_app.config['MODELS_FOLDER'] / model_filename
        
        if not stl_path.exists():
            return jsonify({"success": False, "error": "STL файл не найден"}), 404
        
        ai_service = AiService(current_app.config)
        
        if not ai_service.is_available():
            return jsonify({
                "success": False, 
                "error": "ИИ сервис недоступен. Проверьте настройку OPENAI_API_KEY"
            }), 503
        
        # Получаем информацию о детали
        part_info = _get_part_info(model_path)
        
        # Генерируем параметры
        params = ai_service.generate_gcode_params(stl_path, part_info, requirements)
        
        return jsonify({
            "success": True,
            "parameters": params
        })
        
    except Exception as e:
        current_app.logger.error(f"AI parameter generation error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

def _get_part_info(model_path: str) -> dict:
    """Получение информации о детали из сохраненных результатов"""
    temp_folder = current_app.config['TEMP_FOLDER']
    
    # Ищем соответствующий файл результата
    for result_file in temp_folder.glob('result_*.json'):
        try:
            result_data = json.loads(result_file.read_text(encoding='utf-8'))
            if result_data.get('model_path') == model_path:
                return result_data
        except Exception:
            continue
    
    # Если не найдено, создаем базовую информацию
    model_filename = Path(model_path).name
    stl_path = current_app.config['MODELS_FOLDER'] / model_filename
    
    if stl_path.exists():
        stl_service = StlService()
        mesh_info = stl_service.analyze_stl(stl_path)
        return {
            "geometry": {"dimensions": {"length": 0, "width": 0, "height": 0}},
            "mesh_info": mesh_info
        }
    
    return {
        "geometry": {"dimensions": {"length": 0, "width": 0, "height": 0}},
        "mesh_info": {"vertices": 0, "faces": 0}
    }