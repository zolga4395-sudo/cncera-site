# 🚀 Complete Setup Guide

Пошаговая инструкция по настройке Combined RSS & Visa Monitor Workflow.

## 📋 Предварительные требования

- ✅ n8n установлен и запущен
- ✅ Доступ к Supabase
- ✅ Telegram аккаунт
- ✅ Firecrawl API key

---

## Шаг 1: Создание Telegram бота

### 1.1 Создать бота

1. Откройте Telegram и найдите [@BotFather](https://t.me/BotFather)
2. Отправьте команду: `/newbot`
3. Следуйте инструкциям:
   - Введите имя бота (например: "Visa Monitor Bot")
   - Введите username (например: "visa_monitor_bot")
4. Сохраните токен бота (например: `8374022565:AAHKrLFwzCEGnnJNFZRyJQnT1-qENUsARnI`)

### 1.2 Создать канал для RSS

1. Создайте новый канал в Telegram
2. Добавьте бота как администратора
3. Получите chat_id канала:

```bash
# Отправьте сообщение в канал, затем выполните:
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates"
```

Chat ID будет в формате: `-1002543695030`

### 1.3 Настроить команды бота

Отправьте [@BotFather](https://t.me/BotFather):

```
/setcommands
```

Выберите своего бота и вставьте:

```
visa - Поиск информации о визах (формат: /visa страна город)
```

---

## Шаг 2: Настройка Supabase

### 2.1 Создать проект

1. Зайдите на [supabase.com](https://supabase.com)
2. Нажмите "New Project"
3. Заполните:
   - Project name: `visa-monitor`
   - Database Password: (надежный пароль)
   - Region: (ближайший к вам)

### 2.2 Создать таблицы

1. Откройте **SQL Editor**
2. Нажмите "New Query"
3. Скопируйте содержимое файла `supabase_setup.sql`
4. Нажмите "Run"

### 2.3 Получить API ключи

1. Перейдите в **Settings → API**
2. Скопируйте:
   - **URL**: `https://xxxxx.supabase.co`
   - **anon public**: `eyJhbGciOiJI...`
   - **service_role**: `eyJhbGciOiJI...` (⚠️ секретный!)

---

## Шаг 3: Получение Firecrawl API Key

### 3.1 Регистрация

1. Зайдите на [firecrawl.dev](https://firecrawl.dev)
2. Нажмите "Get Started" или "Sign Up"
3. Зарегистрируйтесь (GitHub OAuth или email)

### 3.2 Получить ключ

1. После регистрации перейдите в Dashboard
2. Найдите раздел "API Keys"
3. Скопируйте API key: `fc-xxxxxxxxxxxx`
4. Проверьте план:
   - Free tier: ~500 requests/month
   - Для production: рассмотрите платный план

---

## Шаг 4: Импорт Workflow в n8n

### 4.1 Импорт

1. Откройте n8n
2. Нажмите на меню (☰) → **Import from File**
3. Выберите `combined_workflow.json`
4. Нажмите "Import"

### 4.2 Обновить учетные данные

Найдите и обновите следующие nodes:

#### **Supabase nodes** (4 штуки):

```
Supabase: Проверка обработанных
Supabase: Сохранить обработанный
Supabase: Сохранить запрос визы
```

В каждом обновите:
- `apikey` header: ваш anon key (для чтения)
- `Authorization` header: ваш service_role key (для записи)
- URL: замените `emhmgaussusepxubimvo` на ваш project ID

#### **Firecrawl nodes** (3 штуки):

```
Firecrawl: Парсинг страницы
Firecrawl: Поиск посольств
Firecrawl: Страница посольства
```

В каждом обновите:
- `Authorization` header: `Bearer YOUR_FIRECRAWL_KEY`

Или в node "Установка переменных":
- `api_key_firecrawl`: `YOUR_FIRECRAWL_KEY`

#### **Telegram nodes** (4 штуки):

```
Отправить в Telegram (RSS)
Подсказка формата
Отправить результат о визе
Отправить: не найдено
```

В каждом обновите URL:
- Замените `8374022565:AAHKrLFwzCEGnnJNFZRyJQnT1-qENUsARnI` на ваш bot token

В node "Отправить в Telegram (RSS)":
- `chat_id`: замените на ID вашего канала

---

## Шаг 5: Настройка Webhook

### 5.1 Получить Webhook URL

1. Откройте node "Webhook /telegram"
2. Переключитесь на вкладку "Production"
3. Скопируйте Production URL (например: `https://n8n.example.com/webhook/telegram`)

### 5.2 Установить Webhook для Telegram

Выполните команду:

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-n8n-instance.com/webhook/telegram"}'
```

Проверить webhook:

```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

Ответ должен содержать:
```json
{
  "ok": true,
  "result": {
    "url": "https://your-n8n-instance.com/webhook/telegram",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}
```

---

## Шаг 6: Тестирование

### 6.1 Тест RSS Workflow

**Вариант 1: Manual trigger**
1. Откройте workflow в n8n
2. Кликните на node "Запуск по расписанию (RSS)"
3. Нажмите "Execute Node"

**Вариант 2: Wait for schedule**
- Workflow запустится автоматически через 3 часа

**Проверка:**
- ✅ В канале появились новости
- ✅ В Supabase таблице `processed_urls` есть записи

### 6.2 Тест Visa Workflow

1. Откройте своего бота в Telegram
2. Отправьте: `/visa Польша Ташкент`

**Ожидаемый результат:**
```
🏛 Информация о визе: Польша Ташкент

✅ Возможна запись!
На сайте найдены признаки доступных слотов для записи.

🔗 Сайт: https://...

📧 Email:
  • visa@poland-embassy.uz

☎️ Телефоны:
  • +998 71 XXX XX XX

💡 Рекомендуем связаться с посольством для уточнения деталей
```

**Проверка:**
- ✅ Бот ответил в течение 10-15 секунд
- ✅ В Supabase таблице `visa_queries` есть запись

### 6.3 Проверка ошибок

Откройте в n8n:
- **Executions** → проверьте статус выполнений
- Должно быть: ✅ Success
- Если ❌ Error → проверьте логи

---

## Шаг 7: Настройка окружения (опционально)

### 7.1 Использование переменных окружения

Вместо хардкода ключей в workflow:

1. В n8n создайте credentials:
   - Settings → Credentials → Add Credential
   - Выберите "HTTP Request" или "Generic"

2. Или используйте Environment Variables:

```bash
# В .env файле n8n
FIRECRAWL_API_KEY=fc-xxxx
TELEGRAM_BOT_TOKEN=xxxx
SUPABASE_ANON_KEY=xxxx
SUPABASE_SERVICE_KEY=xxxx
```

3. В workflow используйте:
```javascript
{{ $env.FIRECRAWL_API_KEY }}
{{ $env.TELEGRAM_BOT_TOKEN }}
```

### 7.2 Настройка расписания

По умолчанию RSS проверяется каждые 3 часа.

Изменить:
1. Откройте node "Запуск по расписанию (RSS)"
2. Измените `hoursInterval`: 
   - `1` = каждый час
   - `6` = каждые 6 часов
   - `24` = раз в день

Или используйте Cron:
```
0 */3 * * *  # Каждые 3 часа
0 9 * * *    # Каждый день в 9:00
0 9,18 * * * # В 9:00 и 18:00
```

---

## Шаг 8: Мониторинг и обслуживание

### 8.1 Мониторинг выполнений

**В n8n:**
- Executions → фильтр по workflow
- Проверяйте ошибки регулярно

**В Supabase:**
```sql
-- Проверка RSS обработки
SELECT COUNT(*) as total, DATE(processed_at) as date 
FROM processed_urls 
GROUP BY DATE(processed_at) 
ORDER BY date DESC 
LIMIT 7;

-- Проверка visa запросов
SELECT query, COUNT(*) as count 
FROM visa_queries 
GROUP BY query 
ORDER BY count DESC 
LIMIT 10;
```

### 8.2 Очистка старых данных

Автоматическая очистка (настройте cron в Supabase):

```sql
-- Удалить обработанные URL старше 30 дней
SELECT cleanup_old_processed_urls();

-- Удалить запросы старше 90 дней
SELECT cleanup_old_visa_queries();
```

Или настройте pg_cron:
```sql
SELECT cron.schedule(
  'cleanup-urls',
  '0 3 * * *',  -- Каждый день в 3:00
  'SELECT cleanup_old_processed_urls()'
);
```

### 8.3 Резервное копирование

**Supabase:**
- Settings → Database → Daily backups (включено по умолчанию)

**n8n workflow:**
- Регулярно экспортируйте: Menu → Export

---

## 🔧 Troubleshooting

### Проблема: Бот не отвечает

**Решение:**
1. Проверьте webhook:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
   ```
2. Проверьте n8n executions для ошибок
3. Убедитесь, что webhook URL доступен публично
4. Проверьте SSL сертификат (Telegram требует HTTPS)

### Проблема: RSS не обрабатывается

**Решение:**
1. Проверьте доступность RSS feed
2. Проверьте Firecrawl лимиты (Dashboard)
3. Проверьте Supabase connection
4. Увеличьте таймауты в Firecrawl nodes

### Проблема: Дублирующиеся посты

**Решение:**
1. Проверьте таблицу `processed_urls`
2. Убедитесь, что UNIQUE constraint на `url` активен
3. Проверьте логику IF node "Если не обработан"

### Проблема: Firecrawl ошибки 429 (Too Many Requests)

**Решение:**
1. Увеличьте `Wait` delay между элементами
2. Проверьте свой plan на firecrawl.dev
3. Рассмотрите upgrade плана
4. Уменьшите частоту проверки RSS

---

## 📊 Рекомендации по Production

### Безопасность:
- ✅ Используйте environment variables
- ✅ Никогда не комитьте API ключи
- ✅ Включите RLS в Supabase
- ✅ Ограничьте webhook access (IP whitelist)
- ✅ Регулярно ротируйте API keys

### Производительность:
- ✅ Настройте подходящие таймауты
- ✅ Мониторьте API лимиты
- ✅ Используйте кэширование где возможно
- ✅ Оптимизируйте regex в extractors

### Надежность:
- ✅ Настройте error notifications
- ✅ Добавьте retry логику
- ✅ Регулярное резервное копирование
- ✅ Мониторинг uptime

---

## ✅ Checklist после установки

- [ ] Telegram бот создан и токен получен
- [ ] Telegram канал создан и chat_id получен
- [ ] Supabase проект создан
- [ ] Таблицы в Supabase созданы
- [ ] Firecrawl API key получен
- [ ] Workflow импортирован в n8n
- [ ] Все API ключи обновлены в workflow
- [ ] Webhook настроен для Telegram
- [ ] RSS workflow протестирован
- [ ] Visa workflow протестирован
- [ ] Мониторинг настроен
- [ ] Резервное копирование настроено

---

## 🎉 Готово!

Ваш Combined RSS & Visa Monitor Workflow настроен и готов к работе!

**Следующие шаги:**
1. Настройте дополнительные RSS feeds
2. Добавьте больше источников для visa поиска
3. Настройте уведомления об ошибках
4. Рассмотрите масштабирование (multiple bots, channels)

**Поддержка:**
- Документация: `WORKFLOW_DOCUMENTATION.md`
- Диаграммы: `WORKFLOW_DIAGRAM.md`
- Issues: создайте на GitHub

---

**Happy Automating! 🚀**
