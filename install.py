#!/usr/bin/env python3
"""
CNCera v2.0 - Скрипт установки
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

def run_command(cmd, description):
    """Выполнить команду с описанием"""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} - успешно")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - ошибка: {e.stderr}")
        return False

def check_python_version():
    """Проверить версию Python"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"❌ Требуется Python 3.8+, установлен {version.major}.{version.minor}")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return True

def install_requirements():
    """Установить зависимости Python"""
    if not Path("requirements.txt").exists():
        print("❌ Файл requirements.txt не найден")
        return False
    
    return run_command(f"{sys.executable} -m pip install -r requirements.txt", "Установка зависимостей Python")

def create_directories():
    """Создать необходимые директории"""
    directories = ["temp", "models", "static", "logs"]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✅ Создана директория: {directory}")
    
    return True

def check_freecad():
    """Проверить наличие FreeCAD"""
    freecad_paths = [
        "FreeCADCmd",
        "FreeCADCmd.exe",
        "/usr/bin/FreeCADCmd",
        "/usr/local/bin/FreeCADCmd",
        "/opt/freecad/bin/FreeCADCmd"
    ]
    
    for path in freecad_paths:
        if subprocess.run(f"which {path}", shell=True, capture_output=True).returncode == 0:
            print(f"✅ FreeCAD найден: {path}")
            return True
    
    print("⚠️  FreeCAD не найден. Установите FreeCAD для работы с STEP файлами")
    print("   Скачать: https://www.freecadweb.org/downloads.php")
    return False

def main():
    """Основная функция установки"""
    print("🚀 CNCera v2.0 - Установка")
    print("=" * 40)
    
    # Проверка Python
    if not check_python_version():
        sys.exit(1)
    
    # Создание директорий
    if not create_directories():
        sys.exit(1)
    
    # Установка зависимостей
    if not install_requirements():
        print("❌ Ошибка установки зависимостей")
        sys.exit(1)
    
    # Проверка FreeCAD
    check_freecad()
    
    print("\n" + "=" * 40)
    print("✅ Установка завершена!")
    print("\n📋 Следующие шаги:")
    print("1. Запустите приложение: python run.py")
    print("2. Откройте браузер: http://localhost:5000")
    print("3. Загрузите STL или STEP файл")
    print("4. Сгенерируйте G-code")
    
    print("\n🔧 Дополнительные настройки:")
    print("- Для работы с STEP файлами установите FreeCAD")
    print("- Для превью изображений установите matplotlib")
    print("- Проверьте статус: http://localhost:5000/api/status")

if __name__ == "__main__":
    main()