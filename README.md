# CNCera - 3D Analysis & G-code Generation

Система для анализа 3D-геометрии и генерации G-кода для ЧПУ станков.

## Возможности

- **Анализ 3D-моделей**: STEP/STL файлы
- **Генерация G-кода**: Поддержка 5 контроллеров (Fanuc, Siemens, Heidenhain, GSK, Mazak)
- **Операции**: Фрезерование, точение, сверление, фаски
- **3D-просмотрщик**: Интерактивный просмотр моделей
- **ИИ-интеграция**: Чат с OpenAI, Claude, Grok

## Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Установите FreeCAD для конвертации STEP файлов:
- Windows: [FreeCAD](https://www.freecadweb.org/downloads.php)
- Linux: `sudo apt install freecad`
- macOS: `brew install freecad`

3. Настройте переменные окружения (опционально):
```bash
export OPENAI_API_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"
export XAI_API_KEY="your-key"
```

## Запуск

```bash
python app.py
```

Откройте http://127.0.0.1:5000 в браузере.

## Использование

1. Загрузите 3D-модель (STEP/STL)
2. Настройте параметры обработки
3. Выберите контроллер и тип операции
4. Сгенерируйте G-код
5. Скачайте готовый файл

## Поддерживаемые контроллеры

- **Fanuc**: Стандартный G-код
- **Siemens**: Sinumerik ISO
- **Heidenhain**: TNC конверсационный
- **GSK**: Китайские контроллеры
- **Mazak**: EIA/ISO совместимый

## Операции

- **Фрезерование**: Растр, адаптивная, waterline
- **Точение**: Черновая/чистовая, подрезка торца
- **Сверление**: G81/G82/G83 циклы
- **Фаски**: Контурная обработка