"""
Утилиты для работы с файлами
"""

import hashlib
from pathlib import Path
from typing import Optional
from flask import request

def get_uploaded_size(fs) -> int:
    """Безопасное определение размера загружаемого файла"""
    try:
        cl = getattr(fs, "content_length", None)
        if isinstance(cl, int) and cl >= 0:
            return cl
    except Exception:
        pass
    
    try:
        stream = getattr(fs, "stream", None)
        if stream is not None and hasattr(stream, "tell") and hasattr(stream, "seek"):
            pos = stream.tell()
            stream.seek(0, 2)  # SEEK_END
            size = stream.tell()
            stream.seek(pos, 0)  # SEEK_SET back
            if isinstance(size, int) and size >= 0:
                return size
    except Exception:
        pass
    
    try:
        hdr = request.headers.get("Content-Length")
        if hdr is not None:
            return int(hdr)
    except Exception:
        pass
    
    return 0

def generate_file_hash(file_path: Path) -> str:
    """Генерация хеша файла"""
    return hashlib.md5(str(file_path).encode()).hexdigest()

def safe_filename(filename: str) -> str:
    """Безопасное имя файла"""
    from werkzeug.utils import secure_filename
    return secure_filename(filename)

def ensure_directory(directory: Path) -> None:
    """Создание директории если не существует"""
    directory.mkdir(parents=True, exist_ok=True)

def cleanup_temp_files(*file_paths: Path) -> None:
    """Очистка временных файлов"""
    for path in file_paths:
        try:
            if path and path.exists():
                path.unlink()
        except Exception:
            pass