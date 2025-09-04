#!/usr/bin/env python3
"""
CNCera v2.0 - Тестирование API
"""

import requests
import json
import time
from pathlib import Path

API_BASE = "http://localhost:5000"

def test_status():
    """Тест статуса API"""
    print("🔍 Тестирование статуса API...")
    try:
        response = requests.get(f"{API_BASE}/api/status")
        if response.status_code == 200:
            data = response.json()
            print("✅ API доступен")
            print(f"   Версия: {data.get('version', 'unknown')}")
            print(f"   Статус: {data.get('status', 'unknown')}")
            print(f"   FreeCAD: {'✅' if data.get('features', {}).get('freecad_available') else '❌'}")
            print(f"   Matplotlib: {'✅' if data.get('features', {}).get('matplotlib_available') else '❌'}")
            return True
        else:
            print(f"❌ API недоступен: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return False

def test_upload():
    """Тест загрузки файла"""
    print("\n📤 Тестирование загрузки файла...")
    
    # Создаем тестовый STL файл
    test_stl = create_test_stl()
    if not test_stl:
        print("❌ Не удалось создать тестовый STL файл")
        return False
    
    try:
        with open(test_stl, 'rb') as f:
            files = {'file': ('test.stl', f, 'model/stl')}
            data = {
                'units': 'mm',
                'linear_deflection': '0.1',
                'angular_deflection_deg': '15'
            }
            
            response = requests.post(f"{API_BASE}/upload", files=files, data=data)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print("✅ Файл успешно загружен")
                    print(f"   Модель: {result.get('model_path', 'unknown')}")
                    return result.get('model_path')
                else:
                    print(f"❌ Ошибка загрузки: {result.get('error', 'unknown')}")
                    return False
            else:
                print(f"❌ HTTP ошибка: {response.status_code}")
                print(f"   Ответ: {response.text}")
                return False
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        return False
    finally:
        # Удаляем тестовый файл
        try:
            Path(test_stl).unlink()
        except:
            pass

def test_gcode_generation(model_path):
    """Тест генерации G-code"""
    print("\n⚙️ Тестирование генерации G-code...")
    
    if not model_path:
        print("❌ Нет модели для тестирования")
        return False
    
    try:
        data = {
            'model_path': model_path,
            'controller': 'fanuc',
            'operation_type': 'milling',
            'tool': 3.0,
            'feed': 300.0,
            'spindle': 8000,
            'stepover': 0.4,
            'clearance': 5.0
        }
        
        response = requests.post(
            f"{API_BASE}/generate_gcode",
            json=data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("✅ G-code успешно сгенерирован")
                print(f"   Файл: {result.get('gcode_path', 'unknown')}")
                print(f"   Контроллер: {result.get('controller', 'unknown')}")
                print(f"   Операция: {result.get('operation', 'unknown')}")
                return True
            else:
                print(f"❌ Ошибка генерации: {result.get('error', 'unknown')}")
                return False
        else:
            print(f"❌ HTTP ошибка: {response.status_code}")
            print(f"   Ответ: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Ошибка генерации: {e}")
        return False

def create_test_stl():
    """Создать простой тестовый STL файл"""
    try:
        # Простой ASCII STL файл (куб)
        stl_content = """solid test_cube
  facet normal 0.0 0.0 1.0
    outer loop
      vertex 0.0 0.0 1.0
      vertex 1.0 0.0 1.0
      vertex 1.0 1.0 1.0
    endloop
  endfacet
  facet normal 0.0 0.0 1.0
    outer loop
      vertex 0.0 0.0 1.0
      vertex 1.0 1.0 1.0
      vertex 0.0 1.0 1.0
    endloop
  endfacet
  facet normal 0.0 0.0 -1.0
    outer loop
      vertex 0.0 0.0 0.0
      vertex 0.0 1.0 0.0
      vertex 1.0 1.0 0.0
    endloop
  endfacet
  facet normal 0.0 0.0 -1.0
    outer loop
      vertex 0.0 0.0 0.0
      vertex 1.0 1.0 0.0
      vertex 1.0 0.0 0.0
    endloop
  endfacet
  facet normal 0.0 1.0 0.0
    outer loop
      vertex 0.0 1.0 0.0
      vertex 0.0 1.0 1.0
      vertex 1.0 1.0 1.0
    endloop
  endfacet
  facet normal 0.0 1.0 0.0
    outer loop
      vertex 0.0 1.0 0.0
      vertex 1.0 1.0 1.0
      vertex 1.0 1.0 0.0
    endloop
  endfacet
  facet normal 0.0 -1.0 0.0
    outer loop
      vertex 0.0 0.0 0.0
      vertex 1.0 0.0 0.0
      vertex 1.0 0.0 1.0
    endloop
  endfacet
  facet normal 0.0 -1.0 0.0
    outer loop
      vertex 0.0 0.0 0.0
      vertex 1.0 0.0 1.0
      vertex 0.0 0.0 1.0
    endloop
  endfacet
  facet normal 1.0 0.0 0.0
    outer loop
      vertex 1.0 0.0 0.0
      vertex 1.0 1.0 0.0
      vertex 1.0 1.0 1.0
    endloop
  endfacet
  facet normal 1.0 0.0 0.0
    outer loop
      vertex 1.0 0.0 0.0
      vertex 1.0 1.0 1.0
      vertex 1.0 0.0 1.0
    endloop
  endfacet
  facet normal -1.0 0.0 0.0
    outer loop
      vertex 0.0 0.0 0.0
      vertex 0.0 0.0 1.0
      vertex 0.0 1.0 1.0
    endloop
  endfacet
  facet normal -1.0 0.0 0.0
    outer loop
      vertex 0.0 0.0 0.0
      vertex 0.0 1.0 1.0
      vertex 0.0 1.0 0.0
    endloop
  endfacet
endsolid test_cube"""
        
        test_file = Path("test_cube.stl")
        test_file.write_text(stl_content)
        return str(test_file)
    except Exception as e:
        print(f"❌ Ошибка создания тестового файла: {e}")
        return None

def main():
    """Основная функция тестирования"""
    print("🧪 CNCera v2.0 - Тестирование API")
    print("=" * 40)
    
    # Тест 1: Статус API
    if not test_status():
        print("\n❌ API недоступен. Убедитесь, что сервер запущен:")
        print("   python run.py")
        return
    
    # Тест 2: Загрузка файла
    model_path = test_upload()
    if not model_path:
        print("\n❌ Тест загрузки не прошел")
        return
    
    # Тест 3: Генерация G-code
    if not test_gcode_generation(model_path):
        print("\n❌ Тест генерации G-code не прошел")
        return
    
    print("\n" + "=" * 40)
    print("✅ Все тесты прошли успешно!")
    print("\n🎉 CNCera v2.0 готов к работе!")
    print("   Откройте http://localhost:5000 в браузере")

if __name__ == "__main__":
    main()