"""
Конфигурация backend сервера
"""

import os
import shutil
from pathlib import Path

class Config:
    """Базовая конфигурация"""
    
    # Основные настройки Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Директории
    BASE_DIR = Path(__file__).parent.parent.resolve()
    TEMP_FOLDER = BASE_DIR / 'temp'
    MODELS_FOLDER = BASE_DIR / 'models'
    STATIC_FOLDER = BASE_DIR / 'static'
    
    # Лимиты загрузки
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
    
    # Поддерживаемые форматы
    ALLOWED_EXTENSIONS = {'.step', '.stp', '.stl'}
    
    # FreeCAD настройки
    FREECAD_CMD = None
    FREECAD_TIMEOUT = 600  # 10 минут
    
    # OpenAI настройки
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    
    # CAM настройки
    MAX_CAM_POINTS = 40000
    DEFAULT_TOOL_DIAMETER = 3.0
    DEFAULT_FEED_RATE = 300.0
    DEFAULT_SPINDLE_SPEED = 8000
    
    def __init__(self):
        # Поиск FreeCAD
        self.FREECAD_CMD = self._locate_freecad()
    
    def _locate_freecad(self):
        """Поиск FreeCADCmd"""
        # Проверяем переменные окружения
        for key in ("FREECADCMD_PATH", "FREECADCMD"):
            val = os.environ.get(key)
            if val and os.path.isfile(val):
                return val
        
        # Проверяем PATH
        for name in ("FreeCADCmd.exe", "FreeCADCmd"):
            path = shutil.which(name)
            if path:
                return path
        
        # Стандартные пути
        patterns = [
            r"C:/Program Files/FreeCAD*/bin/FreeCADCmd*.exe",
            r"C:/Program Files (x86)/FreeCAD*/bin/FreeCADCmd*.exe",
            "/usr/bin/FreeCADCmd",
            "/usr/local/bin/FreeCADCmd",
            "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd"
        ]
        
        import glob
        for pattern in patterns:
            matches = glob.glob(pattern)
            for match in matches:
                if os.path.isfile(match):
                    return match
        
        return None

class DevelopmentConfig(Config):
    """Конфигурация для разработки"""
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    """Конфигурация для продакшена"""
    DEBUG = False
    TESTING = False

class TestingConfig(Config):
    """Конфигурация для тестирования"""
    DEBUG = True
    TESTING = True
    WTF_CSRF_ENABLED = False

# Выбор конфигурации по переменной окружения
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

def get_config():
    return config.get(os.environ.get('FLASK_ENV', 'default'), DevelopmentConfig)