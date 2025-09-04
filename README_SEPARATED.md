# CNCera - Разделенная архитектура

Проект теперь разделен на **Backend API** и **Frontend** приложение для лучшей масштабируемости и разработки.

## 🏗️ Архитектура

```
CNCera/
├── backend/                 # 🐍 Python Flask API
│   ├── app.py              # Основной сервер приложения
│   ├── config/             # Конфигурация
│   ├── routes/             # API маршруты
│   ├── services/           # Бизнес-логика
│   ├── utils/              # Утилиты
│   ├── requirements.txt    # Python зависимости
│   └── run.py             # Скрипт запуска
│
├── frontend/               # 🌐 JavaScript Frontend
│   ├── src/               # Исходный код
│   ├── public/            # Статические файлы
│   ├── package.json       # Node.js зависимости
│   └── webpack.config.js  # Конфигурация сборки
│
└── README_SEPARATED.md    # Эта документация
```

## 🚀 Быстрый старт

### 1. Backend (API Server)

```bash
# Переходим в директорию backend
cd backend

# Устанавливаем Python зависимости
pip install -r requirements.txt

# Настраиваем переменные окружения
cp .env.example .env
# Отредактируйте .env файл

# Запускаем сервер
python run.py
```

Backend будет доступен на: http://127.0.0.1:5000

### 2. Frontend (Web App)

```bash
# Переходим в директорию frontend
cd frontend

# Устанавливаем Node.js зависимости
npm install

# Настраиваем переменные окружения
cp .env.example .env

# Запускаем dev сервер
npm start
```

Frontend будет доступен на: http://127.0.0.1:3000

## 📡 API Документация

### Основные эндпоинты

#### Health Check
```http
GET /api/health
```

#### Информация о сервисе
```http
GET /api/info
```

#### Загрузка файла
```http
POST /api/upload
Content-Type: multipart/form-data

file: [STEP/STL file]
units: "auto|mm|inch|m"
linear_deflection: 0.1
angular_deflection_deg: 15
relative: false
```

#### ИИ Чат
```http
POST /api/ai/chat
Content-Type: application/json

{
  "message": "Какие параметры для алюминия?",
  "session_id": "session_123",
  "context": {...}
}
```

#### ИИ Анализ
```http
POST /api/ai/analyze
Content-Type: application/json

{
  "model_path": "/api/models/model.stl"
}
```

#### Генерация G-кода
```http
POST /api/gcode/generate
Content-Type: application/json

{
  "model_path": "/api/models/model.stl",
  "tool_diam": 3.0,
  "feed": 300.0,
  "spindle": 8000,
  "controller": "fanuc",
  "operation_type": "milling"
}
```

## 🔧 Конфигурация

### Backend Environment Variables

```bash
# Flask
FLASK_ENV=development
SECRET_KEY=your-secret-key

# Server
BACKEND_HOST=127.0.0.1
BACKEND_PORT=5000

# AI Features
OPENAI_API_KEY=your-openai-key

# FreeCAD
FREECADCMD_PATH=/path/to/FreeCADCmd
```

### Frontend Environment Variables

```bash
# Development
NODE_ENV=development
PORT=3000

# API
REACT_APP_API_URL=http://127.0.0.1:5000/api
```

## 🛠️ Разработка

### Backend

```bash
cd backend

# Установка в режиме разработки
pip install -r requirements.txt

# Запуск с автоперезагрузкой
FLASK_ENV=development python run.py

# Тестирование API
curl http://127.0.0.1:5000/api/health
```

### Frontend

```bash
cd frontend

# Разработка
npm run dev

# Сборка для продакшена
npm run build

# Линтинг
npm run lint
```

## 🐳 Docker

### Backend Dockerfile

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["python", "run.py"]
```

### Frontend Dockerfile

```dockerfile
FROM node:18-alpine

WORKDIR /app
COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=0 /app/dist /usr/share/nginx/html
EXPOSE 80
```

### Docker Compose

```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "5000:5000"
    environment:
      - FLASK_ENV=production
    volumes:
      - ./backend/temp:/app/temp
      - ./backend/models:/app/models

  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend
```

## 📦 Деплой

### Production Backend

```bash
cd backend

# Установка зависимостей
pip install -r requirements.txt

# Настройка переменных
export FLASK_ENV=production
export SECRET_KEY=your-production-secret
export OPENAI_API_KEY=your-key

# Запуск с gunicorn
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:create_app()
```

### Production Frontend

```bash
cd frontend

# Сборка
npm run build

# Деплой на веб-сервер
cp -r dist/* /var/www/html/
```

## 🔍 Отладка

### Backend Logs

```bash
cd backend
tail -f logs/cncera.log
```

### Frontend DevTools

1. Откройте DevTools (F12)
2. Перейдите на вкладку Network
3. Проверьте API запросы

### API Testing

```bash
# Health check
curl http://127.0.0.1:5000/api/health

# Upload test
curl -X POST -F "file=@test.stl" http://127.0.0.1:5000/api/upload
```

## 🤝 Вклад в разработку

1. Fork репозиторий
2. Создайте feature branch
3. Backend: следуйте PEP 8
4. Frontend: используйте ESLint
5. Добавьте тесты
6. Создайте Pull Request

## 📄 Лицензия

MIT License

---

**Разделенная архитектура обеспечивает:**
- ✅ Независимую разработку frontend/backend
- ✅ Масштабируемость сервисов
- ✅ Простоту деплоя
- ✅ Лучшую производительность
- ✅ Возможность создания мобильных приложений