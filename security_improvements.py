# Дополнительные проверки безопасности для CNCera

import re
import os
from pathlib import Path
from typing import Optional, List

class SecurityValidator:
    """Класс для валидации входных данных и обеспечения безопасности"""
    
    @staticmethod
    def validate_filename(filename: str) -> bool:
        """Проверка имени файла на безопасность"""
        if not filename or len(filename) > 255:
            return False
        
        # Запрещенные символы
        forbidden_chars = r'[<>:"/\\|?*\x00-\x1f]'
        if re.search(forbidden_chars, filename):
            return False
            
        # Запрещенные имена
        forbidden_names = {
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }
        
        name_without_ext = Path(filename).stem.upper()
        if name_without_ext in forbidden_names:
            return False
            
        return True
    
    @staticmethod
    def sanitize_path(path: str, base_dir: Path) -> Optional[Path]:
        """Безопасная обработка путей"""
        try:
            # Нормализация пути
            normalized = Path(path).resolve()
            base_resolved = base_dir.resolve()
            
            # Проверка, что путь находится внутри базовой директории
            if not str(normalized).startswith(str(base_resolved)):
                return None
                
            return normalized
        except (OSError, ValueError):
            return None
    
    @staticmethod
    def validate_gcode_params(params: dict) -> dict:
        """Валидация параметров G-кода"""
        validated = {}
        
        # Безопасные диапазоны
        ranges = {
            'tool_diam': (0.1, 50.0),
            'feed': (10.0, 5000.0),
            'spindle': (100, 24000),
            'clearance': (1.0, 50.0),
            'stepover': (0.05, 0.95),
            'stepdown': (0.0, 50.0)
        }
        
        for key, (min_val, max_val) in ranges.items():
            if key in params:
                try:
                    val = float(params[key])
                    validated[key] = max(min_val, min(max_val, val))
                except (ValueError, TypeError):
                    validated[key] = min_val
        
        return validated
    
    @staticmethod
    def validate_controller(controller: str) -> bool:
        """Проверка поддерживаемого контроллера"""
        allowed_controllers = {'fanuc', 'siemens', 'heidenhain', 'gsk', 'mazak'}
        return controller.lower() in allowed_controllers
    
    @staticmethod
    def validate_operation_type(op_type: str) -> bool:
        """Проверка типа операции"""
        allowed_operations = {
            'milling', 'turning', 'drilling', 'chamfer', 
            'roughing', 'finishing'
        }
        return op_type.lower() in allowed_operations

# Дополнительные функции безопасности
def rate_limit_check(client_ip: str, action: str) -> bool:
    """Простая проверка rate limiting"""
    # Здесь можно добавить Redis или другую систему кэширования
    # для отслеживания частоты запросов
    return True

def validate_file_size(file_size: int, max_size: int = 100 * 1024 * 1024) -> bool:
    """Проверка размера файла"""
    return 0 < file_size <= max_size

def sanitize_user_input(text: str, max_length: int = 1000) -> str:
    """Очистка пользовательского ввода"""
    if not text:
        return ""
    
    # Ограничение длины
    text = text[:max_length]
    
    # Удаление потенциально опасных символов
    text = re.sub(r'[<>"\']', '', text)
    
    return text.strip()