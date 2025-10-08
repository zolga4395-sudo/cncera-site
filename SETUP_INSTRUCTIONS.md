# Инструкция по настройке воркфлоу n8n

## ✅ Что было исправлено

### 1. **Вставлены все токены и ключи**
   - ✅ Firecrawl API ключ: `fc-b03e8ca9034a4226bc67449537da847e`
   - ✅ Telegram Bot токен: `8374022565:AAHKrLFwzCEGnnJNFZRyJQnT1-qENUsARnI`
   - ✅ Supabase URL: `https://emhmgaussusepxubimvo.supabase.co`
   - ✅ Supabase Anon Key (для чтения)
   - ✅ Supabase Service Role Key (для записи)

### 2. **Исправлен синтаксис выражений**
   - Заменено `={{` на правильный синтаксис `={{ }}`
   - Исправлены все JSON body для HTTP запросов
   - Обновлены версии узлов IF на typeVersion 2 с правильной структурой

### 3. **Заменен проблемный LLM узел**
   - Узел `@n8n/n8n-nodes-langchain.chainLlm` заменен на простой Code узел
   - Добавлено форматирование текста постов без необходимости подключения LLM

### 4. **Исправлена передача данных между узлами**
   - Добавлено сохранение `chatId` и `query` через все узлы в visa-ветке
   - Добавлено сохранение `url_site` для правильной записи в Supabase

### 5. **Улучшена обработка ошибок**
   - Добавлена проверка на пустые результаты в Code узлах
   - Улучшена логика выбора URL

## 📋 Что нужно сделать ДО импорта

### 1. Настройка Supabase

Создайте две таблицы в вашей Supabase базе данных:

**Таблица `processed_urls`:**
```sql
CREATE TABLE processed_urls (
  id BIGSERIAL PRIMARY KEY,
  url TEXT UNIQUE NOT NULL,
  processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  post_text TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индекс для быстрого поиска
CREATE INDEX idx_processed_urls_url ON processed_urls(url);
```

**Таблица `visa_subscribers`:**
```sql
CREATE TABLE visa_subscribers (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  query TEXT,
  subscribed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(user_id, query)
);

-- Индекс для быстрого поиска подписчиков
CREATE INDEX idx_visa_subscribers_user_id ON visa_subscribers(user_id);
```

### 2. Настройка Telegram бота

1. Получите URL вашего webhook из n8n после импорта воркфлоу
2. Настройте webhook для вашего бота:
   ```bash
   curl -X POST "https://api.telegram.org/bot8374022565:AAHKrLFwzCEGnnJNFZRyJQnT1-qENUsARnI/setWebhook" \
   -H "Content-Type: application/json" \
   -d '{"url": "https://ваш-n8n-домен.com/webhook/telegram"}'
   ```

### 3. Настройка RSS источника

В узле "RSS Reader" замените URL на ваш реальный RSS источник:
```
https://example.com/rss  →  ваш реальный RSS URL
```

### 4. Настройка chat_id для постов RSS

В узле "Отправить в Telegram (RSS)" замените:
```
"@YOUR_CHANNEL_USERNAME"  →  ваш @channel или chat_id
```

Чтобы узнать chat_id канала:
- Отправьте сообщение в канал
- Перейдите на https://api.telegram.org/bot8374022565:AAHKrLFwzCEGnnJNFZRyJQnT1-qENUsARnI/getUpdates
- Найдите ваш chat_id в ответе

## 🚀 Как импортировать воркфлоу

1. Откройте n8n
2. Нажмите на "+" → "Import from file"
3. Выберите файл `n8n_workflow_fixed.json`
4. Воркфлоу будет импортирован в неактивном состоянии
5. Проверьте все узлы
6. Активируйте воркфлоу

## 🔍 Описание воркфлоу

### Ветка 1: RSS мониторинг (каждые 3 часа)
1. Читает RSS ленту
2. Проверяет в Supabase, обрабатывалась ли уже эта ссылка
3. Если нет — парсит страницу через Firecrawl
4. Извлекает контакты (email, телефоны, соцсети)
5. Создает форматированный пост
6. Скачивает скриншот страницы
7. Отправляет в Telegram канал
8. Сохраняет URL в Supabase как обработанный

### Ветка 2: Telegram бот /visa команда (webhook)
1. Получает команду `/visa Страна Город`
2. Формирует поисковый запрос для Firecrawl
3. Ищет сайты посольств через Firecrawl Search
4. Выбирает наиболее подходящий URL
5. Парсит страницу посольства
6. Проверяет наличие свободных слотов
7. Отправляет ответ пользователю
8. Подписывает пользователя на уведомления

### Ветка 3: Автоматический визовый мониторинг (каждые 3 часа)
1. Читает всех подписчиков из Supabase
2. Для каждого подписчика:
   - Ищет сайт посольства
   - Проверяет наличие слотов
   - Отправляет уведомление если есть изменения

## ⚠️ Важные замечания

1. **Firecrawl лимиты**: Бесплатный план Firecrawl имеет ограничения. Следите за использованием API.

2. **Telegram rate limits**: Не отправляйте больше 30 сообщений в секунду.

3. **Supabase**: Убедитесь, что `service_role` ключ используется только для записи данных, а не в публичном коде.

4. **Безопасность**: Этот файл содержит реальные токены! Не публикуйте его в публичных репозиториях.

5. **Webhook URL**: После импорта скопируйте URL webhook'а из узла "Webhook /telegram" и настройте его в вашем Telegram боте.

6. **Тестирование**: Сначала протестируйте каждую ветку воркфлоу отдельно перед активацией всего.

## 🛠 Дополнительные настройки (опционально)

### Изменить интервал проверки
В узлах "Запуск по расписанию" измените `hoursInterval` на нужное значение.

### Добавить фильтры для RSS
В узле "Если не обработан" можно добавить дополнительные условия фильтрации.

### Настроить форматирование постов
Отредактируйте Code узел "Создать пост (Форматирование)" для изменения формата постов.

## 📞 Поддержка

Если возникнут проблемы:
1. Проверьте логи выполнения в n8n
2. Убедитесь, что все таблицы в Supabase созданы
3. Проверьте, что webhook настроен в Telegram
4. Проверьте лимиты API ключей

---

**Статус**: ✅ Воркфлоу готов к импорту
**Дата**: 2025-10-08