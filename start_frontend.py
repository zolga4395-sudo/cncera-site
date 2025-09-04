#!/usr/bin/env python3
"""
CNCera Frontend Startup Script
Запуск frontend приложения с проверками
"""

import os
import sys
import subprocess
import json
from pathlib import Path

def check_node():
    """Проверка Node.js"""
    try:
        result = subprocess.run(['node', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"✅ Node.js {version}")
            return True
        else:
            print("❌ Node.js не найден")
            return False
    except FileNotFoundError:
        print("❌ Node.js не установлен")
        print("   Установите Node.js с https://nodejs.org/")
        return False

def check_npm():
    """Проверка npm"""
    try:
        result = subprocess.run(['npm', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"✅ npm {version}")
            return True
        else:
            print("❌ npm не найден")
            return False
    except FileNotFoundError:
        print("❌ npm не установлен")
        return False

def check_dependencies():
    """Проверка зависимостей Node.js"""
    frontend_dir = Path(__file__).parent / 'frontend'
    package_json = frontend_dir / 'package.json'
    node_modules = frontend_dir / 'node_modules'
    
    if not package_json.exists():
        print("❌ package.json не найден")
        return False
    
    if not node_modules.exists():
        print("⚠️ node_modules не найден")
        return False
    
    print("✅ Зависимости Node.js установлены")
    return True

def install_dependencies():
    """Установка зависимостей Node.js"""
    frontend_dir = Path(__file__).parent / 'frontend'
    
    print("📥 Установка зависимостей Node.js...")
    try:
        result = subprocess.run(['npm', 'install'], 
                              cwd=frontend_dir, 
                              check=True)
        print("✅ Зависимости установлены")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка установки зависимостей: {e}")
        return False

def check_backend():
    """Проверка доступности backend"""
    try:
        import requests
        response = requests.get('http://127.0.0.1:5000/api/health', timeout=5)
        if response.status_code == 200:
            print("✅ Backend сервер доступен")
            return True
        else:
            print("⚠️ Backend сервер недоступен")
            return False
    except Exception:
        print("⚠️ Backend сервер недоступен")
        print("   Запустите backend сервер: python start_backend.py")
        return False

def check_environment():
    """Проверка переменных окружения"""
    frontend_dir = Path(__file__).parent / 'frontend'
    env_file = frontend_dir / '.env'
    env_example = frontend_dir / '.env.example'
    
    if not env_file.exists() and env_example.exists():
        print("⚠️ .env файл не найден")
        print(f"   Скопируйте {env_example} в {env_file}")
        return False
    
    return True

def start_frontend():
    """Запуск frontend сервера"""
    frontend_dir = Path(__file__).parent / 'frontend'
    
    print("🚀 Запуск frontend сервера...")
    
    try:
        # Запуск webpack dev server
        subprocess.run(['npm', 'start'], cwd=frontend_dir, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка запуска frontend: {e}")
        return False
    except KeyboardInterrupt:
        print("\n👋 Frontend сервер остановлен")
        return True

def main():
    print("🌐 CNCera Frontend Startup")
    print("=" * 40)
    
    # Проверки
    if not check_node():
        sys.exit(1)
    
    if not check_npm():
        sys.exit(1)
    
    if not check_dependencies():
        print("📥 Попытка установки зависимостей...")
        if not install_dependencies():
            sys.exit(1)
    
    check_environment()
    check_backend()
    
    # Запуск
    print("=" * 40)
    print("🌐 Frontend будет доступен на: http://127.0.0.1:3000")
    print("📡 Backend API: http://127.0.0.1:5000/api")
    print("=" * 40)
    
    if not start_frontend():
        sys.exit(1)

if __name__ == '__main__':
    main()