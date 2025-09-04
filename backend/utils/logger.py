"""
Настройка логирования для backend
"""

import logging
import sys
from pathlib import Path

def setup_logger(app):
    """Настройка системы логирования"""
    
    # Создаем директорию для логов
    log_dir = Path(app.config['BASE_DIR']) / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    # Настройка форматирования
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Файловый обработчик
    file_handler = logging.FileHandler(log_dir / 'cncera.log')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Настройка логгера приложения
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)
    app.logger.addHandler(console_handler)
    app.logger.addHandler(file_handler)
    
    # Настройка werkzeug логгера
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.WARNING)
    
    app.logger.info("Logger initialized successfully")