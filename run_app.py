#!/usr/bin/env python3
"""
Простой запуск Flask приложения для тестирования
"""

import sys
import os
sys.path.append('.')

# Загружаем .env файл
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Environment variables loaded from .env file")
except ImportError:
    print("⚠️ python-dotenv not installed")

# Импортируем приложение
try:
    import app
    print("✅ Приложение импортировано успешно")
    
    # Проверяем API ключи
    for provider in ["openai", "anthropic", "xai"]:
        key = os.getenv(f"{provider.upper()}_API_KEY")
        if key and key != f"your-{provider}-api-key-here":
            print(f"✅ {provider.upper()} API key найден")
        else:
            print(f"⚠️ {provider.upper()} API key не настроен или имеет значение по умолчанию")
    
    # Запускаем приложение
    print("🚀 Запуск Flask приложения...")
    print("📍 Приложение будет доступно на: http://localhost:5000")
    print("🛑 Для остановки нажмите Ctrl+C")
    
    app.app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
    
except Exception as e:
    print(f"❌ Ошибка запуска: {e}")
    import traceback
    traceback.print_exc()