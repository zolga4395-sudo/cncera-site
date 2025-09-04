# 🚀 CNCera - Быстрый старт

Два файла для полнофункциональной CNC системы с ИИ!

## 📁 Файлы

1. **`cncera_backend.py`** - Backend API сервер (Python Flask)
2. **`cncera_frontend.html`** - Frontend приложение (HTML/JS)

## ⚡ Запуск за 2 минуты

### 1. Backend (обязательно)

```bash
# Установка зависимостей
pip install flask flask-cors matplotlib numpy-stl openai python-dotenv

# Настройка ИИ (опционально)
export OPENAI_API_KEY="your-openai-key"

# Запуск сервера
python cncera_backend.py
```

**Backend запущен:** http://127.0.0.1:5000

### 2. Frontend

Просто откройте `cncera_frontend.html` в браузере!

**Готово! 🎉**

## 🔧 Настройка

### Обязательные зависимости

```bash
pip install flask flask-cors matplotlib numpy-stl
```

### Для ИИ функций (опционально)

```bash
pip install openai
export OPENAI_API_KEY="your-openai-api-key"
```

### Для STEP файлов (опционально)

```bash
# Установите FreeCAD
# Windows: https://www.freecadweb.org/downloads.php
# Linux: sudo apt-get install freecad
# macOS: brew install freecad

export FREECADCMD_PATH="/path/to/FreeCADCmd"
```

## 🎯 Использование

1. **Запустите backend** - `python cncera_backend.py`
2. **Откройте frontend** - `cncera_frontend.html` в браузере
3. **Загрузите 3D файл** - STEP/STP/STL
4. **Используйте ИИ** - анализ, чат, генерация параметров
5. **Сгенерируйте G-код** - для любого контроллера ЧПУ

## ✨ Возможности

### 🤖 ИИ функции
- **Чат-консультант** - "Какие параметры для алюминия?"
- **Анализ детали** - автоматические рекомендации
- **Генерация параметров** - "Нужна быстрая черновая обработка"

### 📊 Анализ
- **3D просмотр** - интерактивная визуализация
- **Анализ геометрии** - размеры, сложность
- **STEP конвертация** - через FreeCAD

### ⚙️ G-код
- **5 контроллеров** - Fanuc, Siemens, Heidenhain, GSK, Mazak  
- **Стратегии** - черновая, чистовая, waterline
- **Готовые программы** - сразу на станок

## 🔍 Проверка работы

### Backend API
```bash
curl http://127.0.0.1:5000/api/health
curl http://127.0.0.1:5000/api/info
```

### Frontend
1. Откройте `cncera_frontend.html`
2. Проверьте статус Backend (зеленый индикатор)
3. Загрузите тестовый STL файл

## 🐛 Решение проблем

### Backend не запускается
```bash
# Проверьте зависимости
pip list | grep flask

# Проверьте порт
lsof -i :5000  # Linux/Mac
netstat -an | find "5000"  # Windows
```

### ИИ не работает
- Проверьте API ключ OpenAI
- Убедитесь в наличии интернета
- Проверьте баланс на аккаунте OpenAI

### STEP файлы не конвертируются
- Установите FreeCAD
- Укажите путь: `export FREECADCMD_PATH="/path/to/FreeCADCmd"`

### Frontend не подключается к Backend
- Убедитесь что Backend запущен на порту 5000
- Проверьте CORS настройки
- Откройте DevTools (F12) и проверьте Network tab

## 🎉 Готово!

Теперь у вас есть полнофункциональная CNC система:
- ✅ Анализ 3D моделей
- ✅ ИИ консультации  
- ✅ Генерация G-кода
- ✅ Поддержка всех основных контроллеров ЧПУ
- ✅ Современный веб-интерфейс

**Просто скопируйте 2 файла и запустите!** 🚀