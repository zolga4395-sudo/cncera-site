"""
Утилиты валидации данных
"""

from pathlib import Path
from typing import Union, Optional

def validate_float(value: Union[str, float, int], 
                  default: float, 
                  min_val: float, 
                  max_val: float) -> float:
    """Валидация и ограничение float значений"""
    try:
        val = float(value)
        return max(min_val, min(max_val, val))
    except (TypeError, ValueError):
        return default

def validate_int(value: Union[str, int, float], 
                default: int, 
                min_val: int, 
                max_val: int) -> int:
    """Валидация и ограничение int значений"""
    try:
        val = int(value)
        return max(min_val, min(max_val, val))
    except (TypeError, ValueError):
        return default

def validate_string(value: Union[str, None], 
                   default: str, 
                   allowed_values: Optional[list] = None) -> str:
    """Валидация строковых значений"""
    if not isinstance(value, str):
        return default
    
    if allowed_values and value not in allowed_values:
        return default
    
    return value

def allowed_file(filename: str, allowed_extensions: set) -> bool:
    """Проверка допустимого расширения файла"""
    return Path(filename).suffix.lower() in allowed_extensions

def validate_coordinates(coords: dict) -> dict:
    """Валидация координат"""
    return {
        'x': validate_float(coords.get('x', 0), 0, -1000, 1000),
        'y': validate_float(coords.get('y', 0), 0, -1000, 1000),
        'z': validate_float(coords.get('z', 0), 0, -1000, 1000)
    }

def validate_gcode_params(params: dict) -> dict:
    """Валидация параметров для генерации G-кода"""
    return {
        'tool_diam': validate_float(params.get('tool_diam', 3.0), 3.0, 0.1, 50.0),
        'stepover': validate_float(params.get('stepover', 0.4), 0.4, 0.05, 0.95),
        'feed': validate_float(params.get('feed', 300.0), 300.0, 10.0, 5000.0),
        'plunge': validate_float(params.get('plunge', 120.0), 120.0, 10.0, 2000.0),
        'clearance': validate_float(params.get('clearance', 5.0), 5.0, 1.0, 50.0),
        'spindle': validate_int(params.get('spindle', 8000), 8000, 1000, 24000) if params.get('spindle') else None,
        'stepdown': validate_float(params.get('stepdown', 0.0), 0.0, 0.0, 50.0),
        'waterline_dz': validate_float(params.get('waterline_dz', 0.0), 0.0, 0.0, 50.0),
        'controller': validate_string(params.get('controller', 'fanuc'), 'fanuc', 
                                    ['fanuc', 'siemens', 'heidenhain', 'gsk', 'mazak']),
        'operation_type': validate_string(params.get('operation_type', 'milling'), 'milling',
                                        ['milling', 'roughing', 'finishing', 'chamfer']),
        'origin': validate_string(params.get('origin', 'bbox_min'), 'bbox_min',
                                ['bbox_min', 'bbox_center', 'bbox_top_center']),
        'dir_axis': validate_string(params.get('dir_axis', 'X'), 'X', ['X', 'Y']),
        'waterline': bool(params.get('waterline', False)),
        'allowance_x': validate_float(params.get('allowance_x', 0.0), 0.0, -10.0, 10.0),
        'allowance_y': validate_float(params.get('allowance_y', 0.0), 0.0, -10.0, 10.0),
        'allowance_z': validate_float(params.get('allowance_z', 0.0), 0.0, -10.0, 10.0)
    }