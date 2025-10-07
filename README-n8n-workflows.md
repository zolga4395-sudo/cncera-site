# Интеллектуальный Агент Мониторинга Цен Конкурентов

Система из двух взаимосвязанных n8n воркфлоу для автоматического мониторинга цен конкурентов с использованием AI (RAG) и векторной базы данных Supabase.

## 📋 Оглавление
- [Архитектура](#архитектура)
- [Требования](#требования)
- [Установка](#установка)
- [Конфигурация](#конфигурация)
- [Использование](#использование)
- [Структура воркфлоу](#структура-воркфлоу)

---

## 🏗 Архитектура

Система состоит из двух воркфлоу:

### **Workflow A: Competitor Price Scraper - MAIN**
Основной воркфлоу, выполняющийся по расписанию (ежедневно в 10:00):
- Получает список конкурентов из Notion
- Парсит веб-страницы конкурентов
- Извлекает цены и описания
- Вызывает RAG Agent для AI-анализа
- Отправляет уведомления в Telegram
- Обновляет данные в Notion

### **Workflow B: Competitor Price Scraper - RAG API**
Вспомогательный воркфлоу (API), предоставляющий AI-анализ:
- Принимает данные через Webhook
- Векторизует данные с OpenAI Embeddings
- Сохраняет в Supabase Vector Store
- Использует Claude (Anthropic) для анализа с учетом исторического контекста
- Возвращает результат анализа

---

## 📦 Требования

### Сервисы и Интеграции
1. **n8n** (v1.0+)
2. **Notion** - для хранения списка конкурентов
3. **Supabase** - для векторной базы данных (RAG)
4. **Anthropic** (Claude) - для AI-анализа
5. **OpenAI** - для векторизации (embeddings)
6. **Telegram** - для уведомлений

### n8n Nodes
Убедитесь, что установлены следующие ноды:
- `@n8n/n8n-nodes-langchain` (для RAG Agent, Vector Store, Embeddings)
- Стандартные ноды: Notion, HTTP Request, Telegram, Code, IF, Set, Webhook

---

## 🚀 Установка

### Шаг 1: Импорт воркфлоу в n8n

1. Скопируйте содержимое файлов:
   - `workflow-a-competitor-price-scraper-main.json`
   - `workflow-b-competitor-price-scraper-rag-api.json`

2. В n8n:
   - Перейдите в раздел **Workflows**
   - Нажмите **Import from File** (или используйте Import from JSON)
   - Импортируйте оба файла

### Шаг 2: Настройка Supabase

В Supabase создайте таблицу для векторного хранилища:

```sql
-- Создание таблицы для хранения векторов
CREATE TABLE competitor_prices (
  id BIGSERIAL PRIMARY KEY,
  content TEXT,
  metadata JSONB,
  embedding vector(1536)
);

-- Создание индекса для быстрого поиска
CREATE INDEX ON competitor_prices USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Создание функции для поиска похожих документов
CREATE OR REPLACE FUNCTION match_documents(
  query_embedding vector(1536),
  match_threshold float,
  match_count int
)
RETURNS TABLE (
  id BIGINT,
  content TEXT,
  metadata JSONB,
  similarity FLOAT
)
LANGUAGE SQL STABLE
AS $$
  SELECT
    competitor_prices.id,
    competitor_prices.content,
    competitor_prices.metadata,
    1 - (competitor_prices.embedding <=> query_embedding) AS similarity
  FROM competitor_prices
  WHERE 1 - (competitor_prices.embedding <=> query_embedding) > match_threshold
  ORDER BY competitor_prices.embedding <=> query_embedding
  LIMIT match_count;
$$;
```

### Шаг 3: Настройка Notion

Создайте базу данных в Notion со следующими полями:

| Поле | Тип | Описание |
|------|-----|----------|
| **Название** | Title | Название конкурента/товара |
| **URL конкурента** | URL | Ссылка на страницу товара |
| **Последняя цена** | Number | Последняя зафиксированная цена |
| **Последний статус** | Rich Text | Результат последнего анализа |
| **Дата проверки** | Date | Дата последней проверки |

---

## ⚙️ Конфигурация

### 1. API Credentials в n8n

Создайте следующие credentials в n8n:

#### **Notion API**
- ID: `NOTION_API`
- Type: Notion API
- Получите Integration Token в Notion: [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)

#### **Supabase API**
- ID: `SUPABASE_API`
- Type: Supabase
- Host: Ваш Supabase Project URL
- Service Role Key: Из Project Settings → API

#### **Anthropic API**
- ID: `ANTHROPIC_API`
- Type: Anthropic
- API Key: Из [https://console.anthropic.com/](https://console.anthropic.com/)

#### **OpenAI API**
- ID: `OPENAI_API`
- Type: OpenAI
- API Key: Из [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)

#### **Telegram API**
- ID: `TELEGRAM_API`
- Type: Telegram
- Получите Bot Token через [@BotFather](https://t.me/BotFather)

### 2. Переменные окружения

Настройте следующие переменные окружения в n8n:

```bash
# Telegram
DUMMY_TELEGRAM_CHAT_ID="-1001234567890"  # ID чата для уведомлений

# Notion
DUMMY_NOTION_DB_ID="abc123def456..."  # ID базы данных конкурентов

# Webhook URL для Workflow B
DUMMY_WEBHOOK_B_URL="https://your-n8n-instance.com/webhook/rag-analysis"

# CSS Селекторы для парсинга
DUMMY_CSS_SELECTOR_PRICE=".price, .product-price, [data-price]"
DUMMY_CSS_SELECTOR_DESCRIPTION=".description, .product-description, .product-info"
```

#### Как получить переменные:

**DUMMY_TELEGRAM_CHAT_ID:**
1. Добавьте бота в группу/канал
2. Отправьте сообщение в группу
3. Откройте: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Найдите `chat.id` в ответе

**DUMMY_NOTION_DB_ID:**
1. Откройте базу данных в Notion
2. Скопируйте ID из URL: `https://notion.so/workspace/<DATABASE_ID>?v=...`

**DUMMY_WEBHOOK_B_URL:**
1. Активируйте Workflow B в n8n
2. Откройте Webhook Trigger node
3. Скопируйте Production Webhook URL

**CSS Селекторы:**
1. Откройте страницу конкурента
2. Используйте DevTools (F12) → Inspector
3. Найдите элемент с ценой/описанием
4. Скопируйте CSS selector (ПКМ → Copy → Copy selector)

---

## 📊 Использование

### Первый запуск

1. **Активируйте Workflow B** (RAG API):
   - Откройте воркфлоу в n8n
   - Нажмите **Active** toggle
   - Скопируйте Webhook URL
   - Сохраните его в `DUMMY_WEBHOOK_B_URL`

2. **Настройте Workflow A** (Main):
   - Убедитесь, что все credentials настроены
   - Добавьте конкурентов в Notion базу данных
   - Протестируйте воркфлоу вручную (Execute Workflow)

3. **Активируйте расписание**:
   - Переключите Workflow A в Active
   - Воркфлоу будет запускаться ежедневно в 10:00

### Ручной запуск

Для тестирования можно запустить воркфлоу вручную:
- Откройте Workflow A
- Нажмите **Execute Workflow**
- Проверьте результаты в Telegram

### Мониторинг

- **Telegram**: Все уведомления приходят в указанный чат
- **Notion**: Обновляется автоматически после каждой проверки
- **n8n Executions**: История выполнений в разделе Executions

---

## 🔧 Структура воркфлоу

### Workflow A: Детальная схема

```
Cron (10:00) 
    ↓
Telegram: "Запуск мониторинга"
    ↓
Notion: Получить список конкурентов
    ↓
HTTP: Загрузить HTML страниц
    ↓
Code: Извлечь цену и описание (cheerio)
    ↓
Code: Рассчитать разницу цен
    ↓
IF: Парсинг успешен?
    ├─ Да → Webhook: Вызов RAG Agent
    │         ├─ Success → IF: Есть изменения?
    │         │              ├─ Да → Telegram: Детальный отчет
    │         │              └─ Нет → (пропуск уведомления)
    │         └─ Error → Telegram: Ошибка RAG
    │
    └─ Нет → Telegram: Ошибка парсинга
                ↓
         Notion: Обновить данные
```

### Workflow B: Детальная схема

```
Webhook: Получить данные от Workflow A
    ↓
Merge: Объединить данные
    ↓
Set: Подготовить текст для векторизации
    ├─→ Supabase: Сохранить в БД (асинхронно)
    │
    └─→ RAG Agent
         ├─ Tool: Vector Store (исторический контекст)
         ├─ Memory: Window Buffer (контекст сессии)
         └─ LLM: Claude (Anthropic)
              ↓
         Set: Подготовить ответ
              ↓
         Respond to Webhook: Вернуть результат
```

---

## 🛠 Troubleshooting

### Проблема: "Ошибка парсинга"

**Решение:**
1. Проверьте CSS селекторы на актуальность
2. Убедитесь, что сайт доступен
3. Проверьте, не блокирует ли сайт боты (User-Agent)

### Проблема: "RAG Agent не отвечает"

**Решение:**
1. Проверьте, активен ли Workflow B
2. Убедитесь, что DUMMY_WEBHOOK_B_URL корректен
3. Проверьте Supabase credentials и таблицу

### Проблема: "Telegram не отправляет сообщения"

**Решение:**
1. Проверьте Bot Token
2. Убедитесь, что бот добавлен в чат
3. Проверьте CHAT_ID (должен начинаться с `-` для групп)

---

## 📝 Дополнительная настройка

### Изменение расписания

В Workflow A измените Cron expression в ноде "Cron Trigger":
```
0 10 * * *   # Ежедневно в 10:00
0 */6 * * *  # Каждые 6 часов
0 9,17 * * * # В 9:00 и 17:00
```

### Настройка порога изменений

В Workflow B измените системный промпт RAG Agent:
```
Если изменение цены больше ±5%  # Измените на нужный процент
```

### Добавление новых полей

1. Добавьте поля в Notion базу данных
2. Измените Code node в Workflow A для извлечения данных
3. Обновите промпт в RAG Agent для учета новых полей

---

## 📄 Лицензия

Эти воркфлоу предоставляются "как есть" для использования и модификации.

## 🤝 Поддержка

При возникновении вопросов:
1. Проверьте логи выполнения в n8n (Executions)
2. Убедитесь, что все credentials настроены
3. Проверьте переменные окружения

---

**Версия:** 1.0.0  
**Дата обновления:** 2025-10-07