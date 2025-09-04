# CNCera v2.0 - Makefile

.PHONY: help install run test clean status

help:
	@echo "CNCera v2.0 - Команды управления"
	@echo "================================="
	@echo "install  - Установка зависимостей"
	@echo "run      - Запуск приложения"
	@echo "test     - Тестирование API"
	@echo "status   - Проверка статуса"
	@echo "clean    - Очистка временных файлов"
	@echo "help     - Показать эту справку"

install:
	@echo "🔧 Установка зависимостей..."
	python install.py

run:
	@echo "🚀 Запуск CNCera v2.0..."
	python run.py

test:
	@echo "🧪 Тестирование API..."
	python test_api.py

status:
	@echo "📊 Проверка статуса..."
	curl -s http://localhost:5000/api/status | python -m json.tool

clean:
	@echo "🧹 Очистка временных файлов..."
	rm -rf temp/* models/* logs/*.log
	@echo "✅ Очистка завершена"

# Запуск в фоновом режиме
run-bg:
	@echo "🚀 Запуск в фоновом режиме..."
	nohup python run.py > logs/server.log 2>&1 &
	@echo "✅ Сервер запущен в фоне (PID: $$!)"

# Остановка фонового процесса
stop:
	@echo "🛑 Остановка сервера..."
	pkill -f "python run.py" || true
	@echo "✅ Сервер остановлен"

# Показать логи
logs:
	@echo "📋 Последние логи:"
	tail -f logs/cncera.log