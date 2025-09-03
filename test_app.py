#!/usr/bin/env python3
"""
Тест для проверки корректности app.py
"""

def test_imports():
    """Тест импортов"""
    try:
        print("Тестируем импорты...")
        import sys
        import os
        
        # Тест основных модулей
        modules = ['json', 'logging', 'pathlib', 'enum', 'dataclasses', 'typing']
        for module in modules:
            __import__(module)
            print(f"✅ {module}")
        
        print("✅ Все стандартные модули импортированы")
        return True
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        return False

def test_app_structure():
    """Тест структуры приложения"""
    try:
        import os
        print("\nТестируем структуру app.py...")
        
        # Тест что файл существует
        if not os.path.exists('app.py'):
            print("❌ Файл app.py не найден")
            return False
        
        # Проверяем размер файла
        with open('app.py', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            line_count = len(lines)
            
        if line_count < 1000:
            print(f"❌ Файл слишком маленький: {line_count} строк")
            return False
            
        print(f"✅ Размер файла: {line_count} строк")
        
        # Проверяем наличие ключевых элементов
        content = ''.join(lines)
        
        required_elements = [
            'INDEX_HTML =',
            '@app.route("/")',
            'class RAGDatabase',
            'class ErrorHandler',
            'class ModelAnalyzer',
            'class EnhancedAIService',
            'class NCViewer',
            'if __name__ == "__main__":'
        ]
        
        for element in required_elements:
            if element in content:
                print(f"✅ {element}")
            else:
                print(f"❌ Отсутствует: {element}")
                return False
                
        print("✅ Все ключевые элементы найдены")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка проверки структуры: {e}")
        return False

def test_flask_routes():
    """Тест маршрутов Flask"""
    try:
        print("\nТестируем маршруты Flask...")
        
        with open('app.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
        routes = [
            '@app.route("/")',
            '@app.route("/upload"',
            '@app.route("/generate_gcode"',
            '@app.route("/ai_chat"',
            '@app.route("/metrics"',
            '@app.route("/health"'
        ]
        
        for route in routes:
            if route in content:
                print(f"✅ {route}")
            else:
                print(f"❌ Отсутствует маршрут: {route}")
                return False
                
        print("✅ Все основные маршруты найдены")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка проверки маршрутов: {e}")
        return False

def test_syntax():
    """Тест синтаксиса Python"""
    try:
        print("\nТестируем синтаксис Python...")
        
        import py_compile
        py_compile.compile('app.py', doraise=True)
        
        print("✅ Синтаксис Python корректен")
        return True
        
    except py_compile.PyCompileError as e:
        print(f"❌ Ошибка синтаксиса: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("🧪 ТЕСТИРОВАНИЕ ПРИЛОЖЕНИЯ CNCera Enhanced")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_app_structure,
        test_flask_routes,
        test_syntax
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
            
    print("\n" + "=" * 50)
    print(f"📊 РЕЗУЛЬТАТ: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Приложение готово к запуску!")
        print("\n🚀 Для запуска выполните:")
        print("python app.py")
        return True
    else:
        print("❌ Есть ошибки, требующие исправления")
        return False

if __name__ == "__main__":
    main()