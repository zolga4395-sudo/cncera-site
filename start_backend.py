#!/usr/bin/env python3
"""
CNCera Backend Startup Script
Запуск backend сервера с проверками
"""

import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Проверка версии Python"""
    if sys.version_info < (3, 8):
        print("❌ Требуется Python 3.8 или новее")
        return False
    print(f"✅ Python {sys.version.split()[0]}")
    return True

def check_dependencies():
    """Проверка зависимостей"""
    backend_dir = Path(__file__).parent / 'backend'
    requirements_file = backend_dir / 'requirements.txt'
    
    if not requirements_file.exists():
        print("❌ Файл requirements.txt не найден")
        return False
    
    print("📦 Проверка зависимостей...")
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'check'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Зависимости в порядке")
            return True
        else:
            print("⚠️ Проблемы с зависимостями:")
            print(result.stdout)
            return False
            
    except Exception as e:
        print(f"❌ Ошибка проверки зависимостей: {e}")
        return False

def install_dependencies():
    """Установка зависимостей"""
    backend_dir = Path(__file__).parent / 'backend'
    requirements_file = backend_dir / 'requirements.txt'
    
    print("📥 Установка зависимостей...")
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', '-r', str(requirements_file)
        ], check=True)
        print("✅ Зависимости установлены")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка установки зависимостей: {e}")
        return False

def check_environment():
    """Проверка переменных окружения"""
    backend_dir = Path(__file__).parent / 'backend'
    env_file = backend_dir / '.env'
    env_example = backend_dir / '.env.example'
    
    if not env_file.exists() and env_example.exists():
        print("⚠️ .env файл не найден")
        print(f"   Скопируйте {env_example} в {env_file} и заполните настройки")
        return False
    
    # Проверка ключевых переменных
    openai_key = os.getenv('OPENAI_API_KEY')
    if openai_key:
        print(f"✅ OpenAI API ключ установлен")
    else:
        print("⚠️ OpenAI API ключ не найден (ИИ функции будут недоступны)")
    
    return True

def start_backend():
    """Запуск backend сервера"""
    backend_dir = Path(__file__).parent / 'backend'
    run_script = backend_dir / 'run.py'
    
    if not run_script.exists():
        print("❌ Скрипт запуска backend не найден")
        return False
    
    print("🚀 Запуск backend сервера...")
    
    # Переходим в директорию backend
    os.chdir(backend_dir)
    
    # Добавляем backend в Python path
    sys.path.insert(0, str(backend_dir))
    
    try:
        # Импортируем и запускаем приложение
        exec(open(run_script).read())
        return True
    except Exception as e:
        print(f"❌ Ошибка запуска backend: {e}")
        return False

def main():
    print("🚀 CNCera Backend Startup")
    print("=" * 40)
    
    # Проверки
    if not check_python_version():
        sys.exit(1)
    
    if not check_dependencies():
        print("📥 Попытка установки зависимостей...")
        if not install_dependencies():
            sys.exit(1)
    
    check_environment()
    
    # Запуск
    print("=" * 40)
    if not start_backend():
        sys.exit(1)

if __name__ == '__main__':
    main()