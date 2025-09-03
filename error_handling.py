# Улучшенная обработка ошибок для CNCera

import logging
import traceback
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass

class ErrorType(Enum):
    """Типы ошибок в системе"""
    FILE_NOT_FOUND = "file_not_found"
    INVALID_FORMAT = "invalid_format"
    PROCESSING_ERROR = "processing_error"
    VALIDATION_ERROR = "validation_error"
    SYSTEM_ERROR = "system_error"
    TIMEOUT_ERROR = "timeout_error"
    PERMISSION_ERROR = "permission_error"

@dataclass
class CNCeraError:
    """Структурированная ошибка"""
    error_type: ErrorType
    message: str
    details: Optional[Dict[str, Any]] = None
    user_message: Optional[str] = None
    retry_possible: bool = False

class ErrorHandler:
    """Централизованная обработка ошибок"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.error_messages = {
            ErrorType.FILE_NOT_FOUND: "Файл не найден",
            ErrorType.INVALID_FORMAT: "Неподдерживаемый формат файла",
            ErrorType.PROCESSING_ERROR: "Ошибка обработки файла",
            ErrorType.VALIDATION_ERROR: "Ошибка валидации параметров",
            ErrorType.SYSTEM_ERROR: "Системная ошибка",
            ErrorType.TIMEOUT_ERROR: "Превышено время ожидания",
            ErrorType.PERMISSION_ERROR: "Ошибка доступа к файлу"
        }
    
    def handle_exception(self, exc: Exception, context: str = "") -> CNCeraError:
        """Обработка исключения с контекстом"""
        error_type = self._classify_exception(exc)
        message = str(exc)
        
        # Логирование с полным traceback
        self.logger.error(f"Error in {context}: {message}", exc_info=True)
        
        # Создание структурированной ошибки
        error = CNCeraError(
            error_type=error_type,
            message=message,
            details={
                "context": context,
                "exception_type": type(exc).__name__,
                "traceback": traceback.format_exc()
            },
            user_message=self._get_user_friendly_message(error_type),
            retry_possible=self._is_retry_possible(error_type)
        )
        
        return error
    
    def _classify_exception(self, exc: Exception) -> ErrorType:
        """Классификация исключения по типу"""
        exc_name = type(exc).__name__
        
        if "FileNotFoundError" in exc_name or "NoSuchFile" in exc_name:
            return ErrorType.FILE_NOT_FOUND
        elif "TimeoutError" in exc_name or "timeout" in str(exc).lower():
            return ErrorType.TIMEOUT_ERROR
        elif "PermissionError" in exc_name or "access" in str(exc).lower():
            return ErrorType.PERMISSION_ERROR
        elif "ValueError" in exc_name or "validation" in str(exc).lower():
            return ErrorType.VALIDATION_ERROR
        elif "OSError" in exc_name or "IOError" in exc_name:
            return ErrorType.SYSTEM_ERROR
        else:
            return ErrorType.PROCESSING_ERROR
    
    def _get_user_friendly_message(self, error_type: ErrorType) -> str:
        """Получение понятного пользователю сообщения"""
        return self.error_messages.get(error_type, "Произошла неизвестная ошибка")
    
    def _is_retry_possible(self, error_type: ErrorType) -> bool:
        """Определение возможности повтора операции"""
        retry_possible = {
            ErrorType.TIMEOUT_ERROR: True,
            ErrorType.SYSTEM_ERROR: True,
            ErrorType.PROCESSING_ERROR: True,
            ErrorType.FILE_NOT_FOUND: False,
            ErrorType.INVALID_FORMAT: False,
            ErrorType.VALIDATION_ERROR: False,
            ErrorType.PERMISSION_ERROR: False
        }
        return retry_possible.get(error_type, False)

def create_error_response(error: CNCeraError) -> Dict[str, Any]:
    """Создание JSON ответа с ошибкой"""
    response = {
        "success": False,
        "error": error.user_message or error.message,
        "error_type": error.error_type.value
    }
    
    if error.retry_possible:
        response["retry_possible"] = True
    
    # В режиме отладки добавляем детали
    import os
    if os.environ.get("DEBUG", "false").lower() == "true":
        response["details"] = error.details
    
    return response

# Декоратор для обработки ошибок в маршрутах
def handle_route_errors(func):
    """Декоратор для автоматической обработки ошибок в маршрутах"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_handler = ErrorHandler(logging.getLogger(__name__))
            error = error_handler.handle_exception(e, f"Route: {func.__name__}")
            return create_error_response(error)
    return wrapper