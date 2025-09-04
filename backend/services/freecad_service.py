"""
Сервис для работы с FreeCAD (конвертация STEP в STL)
"""

import os
import json
import subprocess
import tempfile
import hashlib
from pathlib import Path
from typing import Dict
from string import Template

from utils.validators import validate_float

class FreecadService:
    """Сервис для конвертации STEP/STP в STL через FreeCAD"""
    
    def __init__(self, config):
        self.config = config
        self.freecad_cmd = config.get('FREECAD_CMD')
        self.timeout = config.get('FREECAD_TIMEOUT', 600)
    
    def is_available(self) -> bool:
        """Проверка доступности FreeCAD"""
        return bool(self.freecad_cmd and os.path.isfile(self.freecad_cmd))
    
    def convert_step_to_stl(self, 
                          step_path: Path, 
                          stl_path: Path,
                          linear_deflection: float = 0.1,
                          angular_deflection: float = 15.0,
                          relative: bool = False,
                          units: str = "auto") -> Dict:
        """Конвертация STEP в STL"""
        
        if not self.is_available():
            raise FileNotFoundError("FreeCADCmd не найден. Установите FreeCAD или укажите FREECADCMD_PATH")
        
        # Создаем директорию для STL
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Временные файлы
        sys_tmp = Path(tempfile.gettempdir())
        script_hash = hashlib.md5(str(step_path).encode()).hexdigest()
        tmp_py = sys_tmp / f"fc_{script_hash}.py"
        out_json = sys_tmp / f"fc_{script_hash}_result.json"
        
        try:
            # Подготовка параметров
            lin = validate_float(linear_deflection, 0.1, 0.01, 10.0)
            ang = validate_float(angular_deflection, 15.0, 0.01, 89.0)
            rel = "True" if relative else "False"
            units = units.lower() if units in ("auto", "mm", "inch", "m") else "auto"
            
            # Создание скрипта FreeCAD
            script_content = self._create_conversion_script(
                step_path, stl_path, out_json, lin, ang, rel, units
            )
            
            tmp_py.write_text(script_content, encoding="utf-8")
            
            # Выполнение FreeCAD
            result = self._execute_freecad(tmp_py)
            
            # Чтение результата
            if not out_json.exists():
                raise RuntimeError(f"FreeCAD не создал файл результата: {result}")
            
            result_data = json.loads(out_json.read_text(encoding="utf-8"))
            
            if not result_data.get("success", False):
                raise RuntimeError(f"FreeCAD ошибка: {result_data.get('error', 'неизвестная ошибка')}")
            
            return result_data
            
        finally:
            # Очистка временных файлов
            for temp_file in [tmp_py, out_json]:
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                except Exception:
                    pass
    
    def _create_conversion_script(self, step_path: Path, stl_path: Path, json_path: Path,
                                lin: float, ang: float, rel: str, units: str) -> str:
        """Создание скрипта для FreeCAD"""
        
        # Нормализация путей для разных ОС
        sp = str(step_path).replace("\\", "/")
        tp = str(stl_path).replace("\\", "/")
        jp = str(json_path).replace("\\", "/")
        
        script_template = """
import os, sys, json, traceback, math
import FreeCAD as App
import Part, Mesh, MeshPart

# Параметры
step_path = r"$STEP_PATH"
stl_path = r"$STL_PATH"
json_path = r"$JSON_PATH"
linear_deflection = $LINEAR_DEFLECTION
angular_deflection_deg = $ANGULAR_DEFLECTION
relative = $RELATIVE
units = "$UNITS"

def write_result(result_dict):
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка записи JSON: {e}")

try:
    # Создание документа
    doc = App.newDocument("conversion_doc")
    
    # Импорт STEP файла
    import Import
    Import.insert(step_path, "conversion_doc")
    
    # Получение объектов
    objects = doc.Objects
    if not objects:
        raise Exception("STEP файл не содержит объектов")
    
    # Фильтрация объектов с геометрией
    shape_objects = [obj for obj in objects if hasattr(obj, 'Shape') and obj.Shape is not None]
    if not shape_objects:
        raise Exception("Не найдено объектов с геометрией")
    
    # Объединение геометрии
    if len(shape_objects) == 1:
        combined_shape = shape_objects[0].Shape
    else:
        combined_shape = shape_objects[0].Shape
        for obj in shape_objects[1:]:
            try:
                combined_shape = combined_shape.fuse(obj.Shape)
            except Exception as fuse_error:
                # Если fuse не удался, создаем compound
                try:
                    shapes = [combined_shape] + [obj.Shape for obj in shape_objects[1:]]
                    combined_shape = Part.makeCompound(shapes)
                    break
                except Exception as compound_error:
                    print(f"Ошибка объединения: fuse={fuse_error}, compound={compound_error}")
                    pass
    
    # Масштабирование если нужно
    scale_factors = {"inch": 25.4, "m": 1000.0, "mm": 1.0, "auto": 1.0}
    scale = scale_factors.get(units, 1.0)
    
    if abs(scale - 1.0) > 1e-9:
        matrix = App.Matrix()
        matrix.A11 = scale
        matrix.A22 = scale
        matrix.A33 = scale
        combined_shape = combined_shape.transformGeometry(matrix)
    
    # Получение bounding box
    bbox = combined_shape.BoundBox
    
    # Создание сетки
    try:
        mesh_obj = MeshPart.meshFromShape(
            Shape=combined_shape,
            LinearDeflection=linear_deflection,
            AngularDeflection=math.radians(angular_deflection_deg),
            Relative=relative
        )
        
        # Сохранение STL
        mesh_obj.write(stl_path)
        
        # Подготовка результата
        result = {
            "success": True,
            "error": "",
            "file_info": {
                "filename": os.path.basename(step_path),
                "file_type": ".step",
                "file_size": os.path.getsize(step_path)
            },
            "geometry": {
                "dimensions": {
                    "length": round(bbox.XLength, 3),
                    "width": round(bbox.YLength, 3),
                    "height": round(bbox.ZLength, 3)
                },
                "units": "mm",
                "bounding_box": {
                    "min": [round(bbox.XMin, 3), round(bbox.YMin, 3), round(bbox.ZMin, 3)],
                    "max": [round(bbox.XMax, 3), round(bbox.YMax, 3), round(bbox.ZMax, 3)],
                    "center": [
                        round((bbox.XMin + bbox.XMax) / 2.0, 3),
                        round((bbox.YMin + bbox.YMax) / 2.0, 3),
                        round((bbox.ZMin + bbox.ZMax) / 2.0, 3)
                    ]
                }
            },
            "conversion_settings": {
                "LinearDeflection": linear_deflection,
                "AngularDeflection_deg": angular_deflection_deg,
                "Relative": relative,
                "Units": units,
                "Scale": scale
            },
            "mesh_info": {
                "faces": len(mesh_obj.Facets) if hasattr(mesh_obj, 'Facets') else 0,
                "points": len(mesh_obj.Points) if hasattr(mesh_obj, 'Points') else 0
            }
        }
        
        write_result(result)
        print("Конвертация завершена успешно")
        
    except Exception as mesh_error:
        error_result = {
            "success": False,
            "error": f"Ошибка создания сетки: {str(mesh_error)}",
            "traceback": traceback.format_exc()
        }
        write_result(error_result)
        print(f"Ошибка создания сетки: {mesh_error}")
        
except Exception as main_error:
    error_result = {
        "success": False,
        "error": f"Общая ошибка: {str(main_error)}",
        "traceback": traceback.format_exc()
    }
    write_result(error_result)
    print(f"Общая ошибка: {main_error}")
    traceback.print_exc()
"""
        
        return Template(script_template).substitute(
            STEP_PATH=sp,
            STL_PATH=tp,
            JSON_PATH=jp,
            LINEAR_DEFLECTION=lin,
            ANGULAR_DEFLECTION=ang,
            RELATIVE=rel,
            UNITS=units
        )
    
    def _execute_freecad(self, script_path: Path) -> str:
        """Выполнение скрипта FreeCAD"""
        
        # Настройки процесса
        creationflags = 0x08000000 if os.name == "nt" else 0
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        
        try:
            process = subprocess.run(
                [self.freecad_cmd, str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
                creationflags=creationflags,
                env=env,
                text=True
            )
            
            if process.returncode != 0:
                error_msg = f"FreeCAD завершился с кодом {process.returncode}"
                if process.stderr:
                    error_msg += f"\nSTDERR: {process.stderr[-500:]}"
                if process.stdout:
                    error_msg += f"\nSTDOUT: {process.stdout[-500:]}"
                raise RuntimeError(error_msg)
            
            return process.stdout
            
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"FreeCAD превысил таймаут {self.timeout} секунд")
        except FileNotFoundError:
            raise RuntimeError(f"FreeCAD не найден по пути: {self.freecad_cmd}")
    
    def get_version(self) -> str:
        """Получение версии FreeCAD"""
        if not self.is_available():
            return "недоступен"
        
        try:
            result = subprocess.run(
                [self.freecad_cmd, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                text=True
            )
            return result.stdout.strip() if result.returncode == 0 else "неизвестно"
        except Exception:
            return "ошибка получения версии"