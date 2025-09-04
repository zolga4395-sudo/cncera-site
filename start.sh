#!/bin/bash
# CNCera v2.0 - Скрипт запуска

echo "🚀 CNCera v2.0 - Запуск системы"
echo "================================"

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден. Установите Python 3.8+"
    exit 1
fi

# Проверка версии Python
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Требуется Python 3.8+, установлен $python_version"
    exit 1
fi

echo "✅ Python $python_version найден"

# Создание директорий
echo "📁 Создание директорий..."
mkdir -p temp models static logs

# Проверка зависимостей
echo "🔍 Проверка зависимостей..."
if ! python3 -c "import flask" 2>/dev/null; then
    echo "⚠️  Flask не найден. Устанавливаем зависимости..."
    pip3 install -r requirements.txt
fi

# Проверка FreeCAD
echo "🔧 Проверка FreeCAD..."
if command -v FreeCADCmd &> /dev/null; then
    echo "✅ FreeCAD найден"
else
    echo "⚠️  FreeCAD не найден. Установите для работы с STEP файлами"
fi

# Запуск приложения
echo "🌐 Запуск веб-сервера..."
echo "   URL: http://localhost:5000"
echo "   Для остановки нажмите Ctrl+C"
echo ""

python3 run.py