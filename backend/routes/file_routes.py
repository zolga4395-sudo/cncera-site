"""
Маршруты для работы с файлами (скачивание, просмотр)
"""

from pathlib import Path
from flask import Blueprint, request, send_file, jsonify, current_app

file_bp = Blueprint('files', __name__)

@file_bp.route('/models/<filename>')
def serve_model(filename):
    """Отдача STL моделей и PNG превью"""
    try:
        file_path = current_app.config['MODELS_FOLDER'] / filename
        
        if not file_path.exists():
            return jsonify({"error": "Файл не найден"}), 404
        
        # Определяем MIME тип
        ext = file_path.suffix.lower()
        mime_types = {
            '.stl': 'model/stl',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg'
        }
        
        mimetype = mime_types.get(ext, 'application/octet-stream')
        
        return send_file(
            str(file_path),
            mimetype=mimetype,
            as_attachment=False,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f"Error serving model file {filename}: {e}")
        return jsonify({"error": "Ошибка при отдаче файла"}), 500

@file_bp.route('/files/gcode/<filename>')
def download_gcode(filename):
    """Скачивание G-кода"""
    try:
        file_path = current_app.config['TEMP_FOLDER'] / filename
        
        if not file_path.exists():
            return jsonify({"error": "G-код файл не найден"}), 404
        
        return send_file(
            str(file_path),
            mimetype='text/plain',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f"Error downloading G-code {filename}: {e}")
        return jsonify({"error": "Ошибка при скачивании G-кода"}), 500

@file_bp.route('/files/results/<filename>')
def download_result(filename):
    """Скачивание результатов анализа"""
    try:
        file_path = current_app.config['TEMP_FOLDER'] / filename
        
        if not file_path.exists():
            return jsonify({"error": "Файл результата не найден"}), 404
        
        return send_file(
            str(file_path),
            mimetype='application/json',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f"Error downloading result {filename}: {e}")
        return jsonify({"error": "Ошибка при скачивании результата"}), 500

@file_bp.route('/files/list')
def list_files():
    """Список доступных файлов"""
    try:
        models_folder = current_app.config['MODELS_FOLDER']
        temp_folder = current_app.config['TEMP_FOLDER']
        
        # Список моделей
        models = []
        if models_folder.exists():
            for file_path in models_folder.glob('*'):
                if file_path.is_file():
                    models.append({
                        'name': file_path.name,
                        'size': file_path.stat().st_size,
                        'type': 'model',
                        'url': f'/api/models/{file_path.name}'
                    })
        
        # Список G-кодов
        gcode_files = []
        if temp_folder.exists():
            for file_path in temp_folder.glob('gcode_*.nc'):
                if file_path.is_file():
                    gcode_files.append({
                        'name': file_path.name,
                        'size': file_path.stat().st_size,
                        'type': 'gcode',
                        'url': f'/api/files/gcode/{file_path.name}'
                    })
        
        return jsonify({
            "success": True,
            "models": models,
            "gcode_files": gcode_files,
            "total_models": len(models),
            "total_gcode": len(gcode_files)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error listing files: {e}")
        return jsonify({"error": "Ошибка при получении списка файлов"}), 500

@file_bp.route('/files/cleanup', methods=['POST'])
def cleanup_files():
    """Очистка временных файлов"""
    try:
        temp_folder = current_app.config['TEMP_FOLDER']
        models_folder = current_app.config['MODELS_FOLDER']
        
        cleanup_type = request.get_json().get('type', 'temp')
        
        deleted_count = 0
        
        if cleanup_type in ['temp', 'all']:
            # Очистка временных файлов
            for file_path in temp_folder.glob('*'):
                if file_path.is_file():
                    try:
                        file_path.unlink()
                        deleted_count += 1
                    except Exception:
                        pass
        
        if cleanup_type == 'all':
            # Очистка моделей (осторожно!)
            for file_path in models_folder.glob('*'):
                if file_path.is_file():
                    try:
                        file_path.unlink()
                        deleted_count += 1
                    except Exception:
                        pass
        
        return jsonify({
            "success": True,
            "deleted_files": deleted_count,
            "message": f"Удалено файлов: {deleted_count}"
        })
        
    except Exception as e:
        current_app.logger.error(f"Error during cleanup: {e}")
        return jsonify({"error": "Ошибка при очистке файлов"}), 500