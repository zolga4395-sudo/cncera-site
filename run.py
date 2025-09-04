#!/usr/bin/env python3
"""
CNCera v2.0 - Запуск приложения
"""

import os
import sys
from pathlib import Path

# Добавляем текущую директорию в путь Python
sys.path.insert(0, str(Path(__file__).parent))

# Импортируем и запускаем приложение
from app import app

if __name__ == "__main__":
    print("🚀 Запуск CNCera v2.0...")
    print("📁 Рабочая директория:", os.getcwd())
    print("🌐 Сервер будет доступен по адресу: http://localhost:5000")
    print("📋 API endpoints:")
    print("   POST /upload - Загрузка файлов")
    print("   POST /generate_gcode - Генерация G-code")
    print("   GET  /models/<filename> - Загрузка моделей")
    print("   GET  /download_gcode - Скачивание G-code")
    print("   GET  /api/status - Статус системы")
    print("\n" + "="*50)
    
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=True,
        threaded=True
    )