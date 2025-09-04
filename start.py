#!/usr/bin/env python3
"""
CNCera Startup Script
Запускает CNCera с проверкой зависимостей
"""

import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Проверка версии Python"""
    if sys.version_info < (3, 8):
        print("❌ Требуется Python 3.8 или новее")
        print(f"   Текущая версия: {sys.version}")
        return False
    print(f"✅ Python {sys.version.split()[0]}")
    return True

def check_dependencies():
    """Проверка зависимостей"""
    required_packages = [
        'flask', 'matplotlib', 'numpy-stl', 'openai', 'werkzeug'
    ]
    
    missing = []
    for package in required_packages:
        try:
            if package == 'numpy-stl':
                import stl
            else:
                __import__(package)
            print(f"✅ {package}")
        except ImportError:
            missing.append(package)
            print(f"❌ {package}")
    
    if missing:
        print(f"\n⚠️  Отсутствующие зависимости: {', '.join(missing)}")
        print("   Установите их командой:")
        print("   pip install -r requirements.txt")
        return False
    
    return True

def check_freecad():
    """Проверка FreeCAD"""
    freecad_paths = [
        "FreeCADCmd", "FreeCADCmd.exe",
        "/usr/bin/FreeCADCmd",
        "/usr/local/bin/FreeCADCmd"
    ]
    
    # Проверяем переменные окружения
    for env_var in ["FREECADCMD_PATH", "FREECADCMD"]:
        path = os.environ.get(env_var)
        if path and os.path.isfile(path):
            print(f"✅ FreeCAD найден: {path}")
            return True
    
    # Проверяем PATH
    import shutil
    for cmd in ["FreeCADCmd", "FreeCADCmd.exe"]:
        path = shutil.which(cmd)
        if path:
            print(f"✅ FreeCAD найден в PATH: {path}")
            return True
    
    # Проверяем стандартные пути
    for path in freecad_paths:
        if os.path.isfile(path):
            print(f"✅ FreeCAD найден: {path}")
            return True
    
    print("⚠️  FreeCAD не найден")
    print("   Для работы с STEP файлами установите FreeCAD:")
    print("   - Windows: https://www.freecadweb.org/downloads.php")
    print("   - Linux: sudo apt-get install freecad")
    print("   - macOS: brew install freecad")
    print("   Или установите переменную FREECADCMD_PATH")
    return False

def check_openai_key():
    """Проверка OpenAI API ключа"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        print(f"✅ OpenAI API ключ установлен ({api_key[:8]}...)")
        return True
    else:
        print("⚠️  OpenAI API ключ не найден")
        print("   ИИ функции будут недоступны")
        print("   Установите переменную OPENAI_API_KEY или создайте .env файл")
        return False

def create_directories():
    """Создание необходимых директорий"""
    dirs = ['temp', 'models', 'static']
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)
        print(f"✅ Директория {dir_name}/")

def main():
    print("🚀 Запуск CNCera - AI-Powered CNC System")
    print("=" * 50)
    
    # Проверки
    checks_passed = 0
    total_checks = 5
    
    if check_python_version():
        checks_passed += 1
    
    if check_dependencies():
        checks_passed += 1
    
    if check_freecad():
        checks_passed += 1
    
    if check_openai_key():
        checks_passed += 1
    
    create_directories()
    checks_passed += 1
    
    print("=" * 50)
    print(f"Проверки завершены: {checks_passed}/{total_checks}")
    
    if checks_passed >= 3:  # Минимум для работы
        print("\n🎯 Запуск сервера...")
        
        # Проверяем наличие основного файла
        if Path("main_app.py").exists():
            try:
                # Импортируем и запускаем приложение
                from main_app import app, logger
                
                logger.info("Starting CNCera server with AI capabilities...")
                logger.info("Server will be available at: http://127.0.0.1:5000")
                
                if not os.environ.get("OPENAI_API_KEY"):
                    logger.warning("OpenAI API key not set - AI features will be disabled")
                
                app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
                
            except Exception as e:
                print(f"❌ Ошибка запуска: {e}")
                sys.exit(1)
        else:
            print("❌ Файл main_app.py не найден")
            sys.exit(1)
    else:
        print("\n❌ Слишком много проблем для запуска")
        print("   Устраните ошибки и попробуйте снова")
        sys.exit(1)

if __name__ == "__main__":
    main()