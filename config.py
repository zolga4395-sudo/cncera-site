# Система конфигурации для CNCera

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
import json
from pathlib import Path

@dataclass
class DatabaseConfig:
    """Конфигурация базы данных"""
    type: str = "sqlite"  # sqlite, postgresql, mysql
    host: str = "localhost"
    port: int = 5432
    database: str = "cncera"
    username: str = ""
    password: str = ""
    sqlite_path: str = "cncera.db"

@dataclass
class APIConfig:
    """Конфигурация API ключей"""
    openai_key: str = ""
    anthropic_key: str = ""
    xai_key: str = ""
    timeout: int = 60

@dataclass
class ProcessingConfig:
    """Конфигурация обработки"""
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    temp_dir: str = "temp"
    models_dir: str = "models"
    freecad_path: str = ""
    max_processing_time: int = 600  # 10 минут
    default_linear_deflection: float = 0.1
    default_angular_deflection: float = 15.0

@dataclass
class SecurityConfig:
    """Конфигурация безопасности"""
    secret_key: str = "your-secret-key-change-this"
    rate_limit_requests: int = 100
    rate_limit_window: int = 3600  # 1 час
    allowed_origins: list = None
    enable_cors: bool = True
    
    def __post_init__(self):
        if self.allowed_origins is None:
            self.allowed_origins = ["http://localhost:5000", "http://127.0.0.1:5000"]

@dataclass
class LoggingConfig:
    """Конфигурация логирования"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(levelname)s - %(message)s"
    file_path: str = "cncera.log"
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5

@dataclass
class CNCeraConfig:
    """Основная конфигурация приложения"""
    database: DatabaseConfig = None
    api: APIConfig = None
    processing: ProcessingConfig = None
    security: SecurityConfig = None
    logging: LoggingConfig = None
    
    def __post_init__(self):
        if self.database is None:
            self.database = DatabaseConfig()
        if self.api is None:
            self.api = APIConfig()
        if self.processing is None:
            self.processing = ProcessingConfig()
        if self.security is None:
            self.security = SecurityConfig()
        if self.logging is None:
            self.logging = LoggingConfig()

class ConfigManager:
    """Менеджер конфигурации"""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file = Path(config_file)
        self.config = self._load_config()
    
    def _load_config(self) -> CNCeraConfig:
        """Загрузка конфигурации из файла или переменных окружения"""
        config = CNCeraConfig()
        
        # Загрузка из файла, если существует
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    config = self._dict_to_config(data)
            except Exception as e:
                print(f"Ошибка загрузки конфигурации: {e}")
        
        # Переопределение из переменных окружения
        config = self._load_from_env(config)
        
        return config
    
    def _dict_to_config(self, data: Dict[str, Any]) -> CNCeraConfig:
        """Преобразование словаря в конфигурацию"""
        config = CNCeraConfig()
        
        if 'database' in data:
            config.database = DatabaseConfig(**data['database'])
        if 'api' in data:
            config.api = APIConfig(**data['api'])
        if 'processing' in data:
            config.processing = ProcessingConfig(**data['processing'])
        if 'security' in data:
            config.security = SecurityConfig(**data['security'])
        if 'logging' in data:
            config.logging = LoggingConfig(**data['logging'])
        
        return config
    
    def _load_from_env(self, config: CNCeraConfig) -> CNCeraConfig:
        """Загрузка конфигурации из переменных окружения"""
        
        # API ключи
        config.api.openai_key = os.environ.get("OPENAI_API_KEY", config.api.openai_key)
        config.api.anthropic_key = os.environ.get("ANTHROPIC_API_KEY", config.api.anthropic_key)
        config.api.xai_key = os.environ.get("XAI_API_KEY", config.api.xai_key)
        
        # База данных
        config.database.type = os.environ.get("DB_TYPE", config.database.type)
        config.database.host = os.environ.get("DB_HOST", config.database.host)
        config.database.port = int(os.environ.get("DB_PORT", config.database.port))
        config.database.database = os.environ.get("DB_NAME", config.database.database)
        config.database.username = os.environ.get("DB_USER", config.database.username)
        config.database.password = os.environ.get("DB_PASSWORD", config.database.password)
        
        # Обработка
        config.processing.max_file_size = int(os.environ.get("MAX_FILE_SIZE", config.processing.max_file_size))
        config.processing.freecad_path = os.environ.get("FREECAD_PATH", config.processing.freecad_path)
        config.processing.max_processing_time = int(os.environ.get("MAX_PROCESSING_TIME", config.processing.max_processing_time))
        
        # Безопасность
        config.security.secret_key = os.environ.get("SECRET_KEY", config.security.secret_key)
        config.security.rate_limit_requests = int(os.environ.get("RATE_LIMIT_REQUESTS", config.security.rate_limit_requests))
        
        # Логирование
        config.logging.level = os.environ.get("LOG_LEVEL", config.logging.level)
        config.logging.file_path = os.environ.get("LOG_FILE", config.logging.file_path)
        
        return config
    
    def save_config(self):
        """Сохранение конфигурации в файл"""
        try:
            config_dict = asdict(self.config)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Ошибка сохранения конфигурации: {e}")
    
    def get_config(self) -> CNCeraConfig:
        """Получение текущей конфигурации"""
        return self.config
    
    def update_config(self, **kwargs):
        """Обновление конфигурации"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

# Глобальный экземпляр конфигурации
config_manager = ConfigManager()
config = config_manager.get_config()