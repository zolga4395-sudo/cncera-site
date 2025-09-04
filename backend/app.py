#!/usr/bin/env python3
"""
CNCera Backend API Server
Основной сервер API для системы CNCera
"""

import os
import sys
import logging
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

# Добавляем пути для импортов
sys.path.append(str(Path(__file__).parent))

from config.settings import Config
from routes.upload_routes import upload_bp
from routes.gcode_routes import gcode_bp
from routes.ai_routes import ai_bp
from routes.file_routes import file_bp
from utils.logger import setup_logger

def create_app(config_class=Config):
    """Фабрика приложений Flask"""
    
    # Создаем приложение
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Настраиваем CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
    
    # Middleware для прокси
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    # Настраиваем логирование
    setup_logger(app)
    
    # Регистрируем blueprints
    app.register_blueprint(upload_bp, url_prefix='/api')
    app.register_blueprint(gcode_bp, url_prefix='/api')
    app.register_blueprint(ai_bp, url_prefix='/api')
    app.register_blueprint(file_bp, url_prefix='/api')
    
    # Создаем необходимые директории
    for directory in [app.config['TEMP_FOLDER'], app.config['MODELS_FOLDER'], app.config['STATIC_FOLDER']]:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    # Глобальный обработчик ошибок
    @app.errorhandler(Exception)
    def handle_error(e):
        app.logger.error("Uncaught exception: %s", e, exc_info=True)
        return jsonify({
            "success": False,
            "error": f"Internal server error: {str(e)}"
        }), 500
    
    # Health check endpoint
    @app.route('/api/health')
    def health_check():
        return jsonify({
            "status": "ok",
            "service": "CNCera Backend API",
            "version": "1.0.0"
        })
    
    # API info endpoint
    @app.route('/api/info')
    def api_info():
        return jsonify({
            "name": "CNCera Backend API",
            "version": "1.0.0",
            "features": {
                "ai_chat": bool(os.getenv("OPENAI_API_KEY")),
                "ai_analysis": bool(os.getenv("OPENAI_API_KEY")),
                "freecad_conversion": bool(app.config.get('FREECAD_CMD')),
                "supported_formats": [".step", ".stp", ".stl"],
                "supported_controllers": ["fanuc", "siemens", "heidenhain", "gsk", "mazak"]
            }
        })
    
    return app

if __name__ == '__main__':
    app = create_app()
    
    # Получаем настройки из переменных окружения
    host = os.getenv('BACKEND_HOST', '127.0.0.1')
    port = int(os.getenv('BACKEND_PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    app.logger.info(f"Starting CNCera Backend API server on {host}:{port}")
    app.logger.info("API Documentation: http://{}:{}/api/info".format(host, port))
    
    if not os.getenv("OPENAI_API_KEY"):
        app.logger.warning("OpenAI API key not set - AI features will be disabled")
    
    app.run(host=host, port=port, debug=debug, use_reloader=False)