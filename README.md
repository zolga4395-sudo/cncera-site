# 🤖 Combined RSS & Visa Monitor Workflow

Автоматизированный n8n workflow для мониторинга RSS-лент и поиска визовой информации через Telegram бота.

## 📋 Возможности

### 🔄 RSS Мониторинг
- ✅ Автоматическое чтение RSS-лент (каждые 3 часа)
- ✅ Парсинг статей с извлечением контактов
- ✅ Автоматическая публикация в Telegram
- ✅ Дедупликация обработанных URL
- ✅ Извлечение email, телефонов, соцсетей

### 📱 Visa Мониторинг
- ✅ Telegram бот для запросов о визах
- ✅ Автоматический поиск посольств и визовых центров
- ✅ Проверка наличия доступных слотов
- ✅ Извлечение контактной информации
- ✅ Сохранение истории запросов

## 🚀 Быстрый старт

### 1. Импорт workflow в n8n

1. Откройте n8n
2. Нажмите на меню → Import from File
3. Выберите `combined_workflow.json`
4. Workflow будет импортирован со всеми настройками

### 2. Настройка Supabase

1. Создайте проект в [Supabase](https://supabase.com)
2. Откройте SQL Editor
3. Выполните скрипт из `supabase_setup.sql`
4. Получите API ключи:
   - Settings → API → anon public key
   - Settings → API → service_role key (секретный!)

### 3. Настройка Telegram бота

1. Создайте бота через [@BotFather](https://t.me/BotFather)
2. Получите токен бота
3. Создайте канал/чат для публикаций RSS
4. Получите chat_id канала

### 4. Обновление конфигурации

В workflow обновите следующие параметры:

**Supabase:**
- URL: `https://YOUR_PROJECT.supabase.co`
- Anon Key: `your-anon-key`
- Service Role Key: `your-service-role-key`

**Telegram:**
- Bot Token: `your-bot-token`
- Chat ID (RSS): `your-chat-id`

**Firecrawl:**
- API Key: `your-firecrawl-api-key` (получить на [firecrawl.dev](https://firecrawl.dev))

### 5. Настройка Telegram Webhook

1. В n8n найдите node "Webhook /telegram"
2. Скопируйте Production URL
3. Установите webhook для бота:

```bash
curl -X POST "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "YOUR_N8N_WEBHOOK_URL"}'
```

## 📖 Использование

### RSS Мониторинг

Работает автоматически:
- Проверяет RSS каждые 3 часа
- Парсит новые статьи
- Извлекает контакты
- Публикует в Telegram

### Visa Мониторинг

Отправьте команду боту:

```
/visa Польша Ташкент
/visa Германия Бишкек
/visa США Алматы
```

Формат: `/visa <страна> <город>`

Бот ответит:
- ✅ Статус доступности слотов
- 🔗 Ссылка на сайт посольства
- 📧 Email контакты
- ☎️ Телефоны

## 📁 Структура файлов

```
.
├── combined_workflow.json       # Основной n8n workflow
├── supabase_setup.sql          # SQL скрипт для Supabase
├── WORKFLOW_DOCUMENTATION.md   # Подробная документация
└── README.md                   # Этот файл
```

## 🏗️ Архитектура

### RSS Pipeline:
```
Триггер → RSS Read → Loop → Проверка → Парсинг → 
Контакты → Форматирование → Telegram → Supabase
```

### Visa Pipeline:
```
Webhook → Парсинг команды → Поиск → Выбор URL → 
Парсинг → Проверка слотов → Форматирование → 
Telegram → Supabase
```

## 🔧 Настройки

### Изменить расписание RSS:

В node "Запуск по расписанию (RSS)":
```json
{
  "rule": {
    "interval": [{"field": "hours", "hoursInterval": 3}]
  }
}
```

### Изменить источник RSS:

В node "RSS Read":
```json
{
  "url": "https://your-rss-feed.com/feed/"
}
```

### Изменить задержку между элементами:

В node "Wait":
```json
{
  "amount": 5,
  "unit": "seconds"
}
```

## 📊 Мониторинг

### Supabase Dashboard

**Processed URLs:**
```sql
SELECT COUNT(*) FROM processed_urls;
SELECT * FROM rss_stats;
```

**Visa Queries:**
```sql
SELECT * FROM popular_visa_queries LIMIT 10;
SELECT * FROM recent_visa_queries WHERE has_slots = true;
```

### n8n Executions

Проверяйте вкладку "Executions" в n8n для:
- Истории выполнений
- Ошибок
- Времени выполнения

## 🛡️ Безопасность

1. **Никогда не комитьте API ключи в Git**
2. Используйте переменные окружения в n8n
3. Включите RLS в Supabase для продакшена
4. Регулярно обновляйте токены
5. Ограничьте доступ к webhook endpoints

## 🔍 Troubleshooting

### RSS не обрабатывается:
- Проверьте доступность RSS feed
- Проверьте API лимиты Firecrawl
- Проверьте логи в n8n Executions

### Telegram бот не отвечает:
- Проверьте webhook URL
- Проверьте токен бота
- Проверьте формат команды

### Ошибки Supabase:
- Проверьте API ключи
- Проверьте структуру таблиц
- Проверьте RLS политики

## 📝 TODO / Улучшения

- [ ] Добавить поддержку нескольких RSS источников
- [ ] Уведомления о появлении слотов
- [ ] Статистика по запросам
- [ ] Автоматическая проверка изменений на сайтах
- [ ] Поддержка других языков
- [ ] Rate limiting защита

## 📄 Лицензия

MIT License - используйте свободно!

## 🤝 Поддержка

Для вопросов и предложений:
- Создайте Issue
- Или отправьте Pull Request

---

**Создано с ❤️ для автоматизации рутинных задач**
