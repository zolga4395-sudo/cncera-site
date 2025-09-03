#!/usr/bin/env python3
"""
Простой тест Flask приложения
"""

import sys
sys.path.append('.')

try:
    import app
    print("✅ Импорт app.py успешен")
    
    # Проверяем Flask app
    if hasattr(app, 'app'):
        print("✅ Flask app найден")
        
        # Проверяем маршруты
        routes = [rule.rule for rule in app.app.url_map.iter_rules()]
        print(f"✅ Найдено маршрутов: {len(routes)}")
        for route in routes:
            print(f"  - {route}")
        
        # Проверяем INDEX_HTML
        if hasattr(app, 'INDEX_HTML'):
            print("✅ INDEX_HTML определен")
            print(f"✅ Размер HTML: {len(app.INDEX_HTML)} символов")
        else:
            print("❌ INDEX_HTML не найден")
            
        # Тестируем маршрут "/"
        with app.app.test_client() as client:
            response = client.get('/')
            print(f"✅ Тест маршрута '/': {response.status_code}")
            if response.status_code == 200:
                print("✅ Главная страница работает")
            else:
                print(f"❌ Ошибка главной страницы: {response.status_code}")
                print(f"Ответ: {response.data.decode()[:200]}")
                
    else:
        print("❌ Flask app не найден")
        
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()