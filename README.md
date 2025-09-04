# 🚀 CNCera - AI-Powered CNC Analysis & G-code Generation

Современная система анализа 3D моделей и генерации G-кода с поддержкой искусственного интеллекта. Разделенная архитектура обеспечивает масштабируемость и простоту разработки.

## ✨ Возможности

### 🤖 ИИ Интеграция
- **ИИ Чат-консультант** - Экспертные советы по CNC обработке
- **ИИ Анализ детали** - Автоматические рекомендации по стратегии обработки
- **ИИ Генерация параметров** - Умный подбор режимов резания

### 📊 Анализ и визуализация
- **3D Просмотрщик** - WebGL визуализация с Three.js
- **Поддержка форматов** - STEP/STP (через FreeCAD) и STL
- **Анализ геометрии** - Размеры, сложность, bounding box

### ⚙️ Генерация G-кода
- **5 контроллеров** - Fanuc, Siemens, Heidenhain, GSK, Mazak
- **Различные стратегии** - Черновая, чистовая, waterline
- **CAM алгоритмы** - Raster, marching squares

## 🏗️ Архитектура

```
CNCera/
├── backend/                 # 🐍 Python Flask API
│   ├── app.py              # Основной сервер
│   ├── routes/             # API эндпоинты
│   ├── services/           # Бизнес-логика (AI, FreeCAD, G-code)
│   └── utils/              # Утилиты и валидация
│
├── frontend/               # 🌐 JavaScript Frontend
│   ├── src/               # Исходный код
│   ├── components/        # UI компоненты
│   └── services/          # API клиент
│
├── start_backend.py       # 🐍 Запуск backend
├── start_frontend.py      # 🌐 Запуск frontend  
└── start_all.py          # 🚀 Запуск всего стека
```

## 🚀 Быстрый старт

### Вариант 1: Запуск всего стека одной командой

```bash
# Клонируем репозиторий
git clone <repository-url>
cd cncera

# Запускаем все (backend + frontend)
python start_all.py
```

Откройте браузер: **http://127.0.0.1:3000**

### Вариант 2: Раздельный запуск

#### Backend (API Server)
```bash
# Запуск backend сервера
python start_backend.py
```
Backend API: **http://127.0.0.1:5000**

#### Frontend (Web App)  
```bash
# Запуск frontend приложения
python start_frontend.py
```
Frontend: **http://127.0.0.1:3000**

## 📋 Требования

### Системные требования
- **Python 3.8+**
- **Node.js 16+** (для frontend)
- **FreeCAD** (для STEP файлов)

### ИИ функции (опционально)
- **OpenAI API ключ** - для ИИ консультанта и анализа

## ⚙️ Настройка

### 1. Backend Configuration

```bash
cd backend
cp .env.example .env
```

Отредактируйте `.env`:
```bash
# ИИ функции
OPENAI_API_KEY=your-openai-api-key-here

# FreeCAD (для STEP файлов)
FREECADCMD_PATH=/path/to/FreeCADCmd

# Flask настройки
FLASK_ENV=development
SECRET_KEY=your-secret-key
```

### 2. Frontend Configuration

```bash
cd frontend  
cp .env.example .env
```

### 3. FreeCAD Setup

**Windows:**
```cmd
set FREECADCMD_PATH="C:\Program Files\FreeCAD 0.21\bin\FreeCADCmd.exe"
```

**Linux:**
```bash
sudo apt-get install freecad
export FREECADCMD_PATH="/usr/bin/FreeCADCmd"
```

**macOS:**
```bash
brew install freecad
```

### 4. OpenAI API Key

1. Получите ключ на [OpenAI Platform](https://platform.openai.com/api-keys)
2. Добавьте в `.env` файл backend или экспортируйте:

```bash
export OPENAI_API_KEY="your-api-key-here"
```

## 🎯 Использование

### 1. Загрузка файла
- Выберите STEP/STP или STL файл
- Настройте параметры конвертации
- Нажмите "Анализировать"

### 2. ИИ Анализ  
- После загрузки нажмите "ИИ Анализ"
- Получите рекомендации по обработке

### 3. ИИ Чат
- Задавайте вопросы в чате справа
- Примеры: "Какие параметры для алюминия?", "Объясни waterline"

### 4. ИИ Параметры
- Опишите требования к обработке
- ИИ подберет оптимальные параметры
- Примените их одним кликом

### 5. Генерация G-кода
- Выберите контроллер и операцию
- Настройте параметры инструмента
- Сгенерируйте G-код

## 📡 API Документация

### Health Check
```http
GET /api/health
```

### Загрузка файла
```http
POST /api/upload
Content-Type: multipart/form-data
```

### ИИ Чат
```http
POST /api/ai/chat
{
  "message": "Ваш вопрос",
  "session_id": "session_123"
}
```

### Генерация G-кода
```http
POST /api/gcode/generate
{
  "model_path": "/api/models/model.stl",
  "controller": "fanuc",
  "tool_diam": 3.0,
  "feed": 300.0
}
```

Полная документация API: **http://127.0.0.1:5000/api/info**

## 🛠️ Разработка

### Backend Development
```bash
cd backend
pip install -r requirements.txt
FLASK_ENV=development python run.py
```

### Frontend Development  
```bash
cd frontend
npm install
npm run dev
```

### Тестирование API
```bash
curl http://127.0.0.1:5000/api/health
curl -X POST -F "file=@test.stl" http://127.0.0.1:5000/api/upload
```

## 🐳 Docker

```yaml
# docker-compose.yml
version: '3.8'
services:
  backend:
    build: ./backend
    ports: ["5000:5000"]
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    
  frontend:
    build: ./frontend  
    ports: ["3000:80"]
    depends_on: [backend]
```

```bash
docker-compose up -d
```

## 🔧 Устранение неполадок

### Backend не запускается
```bash
# Проверьте зависимости
cd backend && pip install -r requirements.txt

# Проверьте порт
lsof -i :5000
```

### Frontend не подключается к Backend
```bash
# Проверьте CORS настройки в backend/app.py
# Убедитесь что backend запущен на порту 5000
curl http://127.0.0.1:5000/api/health
```

### FreeCAD не найден
```bash
# Linux
sudo apt-get install freecad
which FreeCADCmd

# Windows - установите FreeCAD и добавьте в PATH
```

### ИИ не работает
```bash
# Проверьте API ключ
echo $OPENAI_API_KEY

# Проверьте баланс на OpenAI
```

## 📈 Производительность

- **Backend**: Flask + Gunicorn для продакшена
- **Frontend**: Webpack с code splitting
- **3D Viewer**: WebGL с оптимизацией
- **Файлы**: Автоматическая очистка временных файлов

## 🤝 Вклад в проект

1. Fork репозиторий
2. Создайте feature branch
3. Backend: следуйте PEP 8
4. Frontend: используйте ESLint  
5. Добавьте тесты
6. Создайте Pull Request

## 📄 Лицензия

MIT License

## 🙏 Благодарности

- **OpenAI** - GPT-4 API для ИИ функций
- **FreeCAD** - STEP/STL конвертация
- **Three.js** - 3D визуализация
- **Flask** - Backend framework
- **Webpack** - Frontend сборка

---

**🎯 Сделано с ❤️ для CNC сообщества**

**🚀 Готово к использованию из коробки!**