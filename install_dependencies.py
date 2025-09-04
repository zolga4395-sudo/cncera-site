#!/usr/bin/env python3
"""
CNCera Dependencies Installer
Автоматическая установка всех необходимых зависимостей
"""

import subprocess
import sys
import os

def install_package(package):
    """Установка Python пакета"""
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
        return True
    except subprocess.CalledProcessError:
        return False

def main():
    print("📦 CNCera Dependencies Installer")
    print("=" * 40)
    
    # Основные зависимости (обязательные)
    required_packages = [
        'flask==2.3.3',
        'flask-cors==4.0.0', 
        'werkzeug==2.3.7',
        'matplotlib==3.7.2',
        'numpy-stl==3.0.1',
        'numpy==1.24.4',
        'pillow==10.0.1'
    ]
    
    # Опциональные зависимости
    optional_packages = [
        'openai==0.28.1',      # Для ИИ функций
        'python-dotenv==1.0.0' # Для .env файлов
    ]
    
    print("🔧 Установка обязательных зависимостей...")
    failed_required = []
    
    for package in required_packages:
        print(f"   Устанавливаю {package}...")
        if install_package(package):
            print(f"   ✅ {package}")
        else:
            print(f"   ❌ {package}")
            failed_required.append(package)
    
    print("\n🌟 Установка опциональных зависимостей...")
    failed_optional = []
    
    for package in optional_packages:
        print(f"   Устанавливаю {package}...")
        if install_package(package):
            print(f"   ✅ {package}")
        else:
            print(f"   ⚠️ {package} (опционально)")
            failed_optional.append(package)
    
    print("\n" + "=" * 40)
    print("📋 Результат установки:")
    
    if not failed_required:
        print("✅ Все обязательные зависимости установлены")
        print("🚀 CNCera готов к запуску!")
        
        if failed_optional:
            print(f"\n⚠️ Опциональные пакеты не установлены: {', '.join(failed_optional)}")
            if 'openai' in str(failed_optional):
                print("   - ИИ функции будут недоступны")
        
        print("\n🎯 Следующие шаги:")
        print("1. python cncera_backend.py  # Запуск backend")
        print("2. Откройте cncera_frontend.html в браузере")
        
    else:
        print(f"❌ Ошибка установки: {', '.join(failed_required)}")
        print("\n🔧 Попробуйте:")
        print("pip install --upgrade pip")
        print("pip install --user <package_name>")
        
        return False
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)