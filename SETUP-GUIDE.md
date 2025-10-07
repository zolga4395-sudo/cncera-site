# Пошаговое Руководство по Настройке
## Интеллектуальный Агент Мониторинга Цен Конкурентов

---

## 📋 Чеклист перед началом

Убедитесь, что у вас есть доступ к:
- [ ] n8n instance (self-hosted или cloud)
- [ ] Notion workspace
- [ ] Supabase project
- [ ] Anthropic API key (Claude)
- [ ] OpenAI API key
- [ ] Telegram bot token

---

## Шаг 1: Настройка Supabase (15 минут)

### 1.1 Создание проекта

1. Перейдите на [https://supabase.com](https://supabase.com)
2. Нажмите **New Project**
3. Заполните:
   - Name: `competitor-price-monitoring`
   - Database Password: (сохраните в безопасном месте)
   - Region: (ближайший к вам)
4. Нажмите **Create new project**

### 1.2 Создание таблицы для векторов

1. Перейдите в **SQL Editor**
2. Нажмите **New query**
3. Вставьте следующий SQL:

```sql
-- Включить расширение для векторов
CREATE EXTENSION IF NOT EXISTS vector;

-- Создать таблицу
CREATE TABLE competitor_prices (
  id BIGSERIAL PRIMARY KEY,
  content TEXT NOT NULL,
  metadata JSONB DEFAULT '{}'::jsonb,
  embedding vector(1536),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Создать индекс для быстрого поиска (IVFFlat)
CREATE INDEX idx_competitor_prices_embedding 
ON competitor_prices 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Функция для поиска похожих документов
CREATE OR REPLACE FUNCTION match_documents(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.5,
  match_count int DEFAULT 5
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
    cp.id,
    cp.content,
    cp.metadata,
    1 - (cp.embedding <=> query_embedding) AS similarity
  FROM competitor_prices cp
  WHERE 1 - (cp.embedding <=> query_embedding) > match_threshold
  ORDER BY cp.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- Добавить комментарии
COMMENT ON TABLE competitor_prices IS 'Хранилище векторных представлений для RAG';
COMMENT ON FUNCTION match_documents IS 'Поиск похожих документов по косинусному сходству';
```

4. Нажмите **Run** (или F5)
5. Проверьте, что таблица создана: Table Editor → competitor_prices

### 1.3 Получение API credentials

1. Перейдите в **Settings** → **API**
2. Скопируйте:
   - **Project URL** (например: `https://abcdefgh.supabase.co`)
   - **Service Role Key** (не anon key!)
3. Сохраните эти данные - они понадобятся в n8n

---

## Шаг 2: Настройка Notion (10 минут)

### 2.1 Создание Integration

1. Перейдите на [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Нажмите **+ New integration**
3. Заполните:
   - Name: `Competitor Price Scraper`
   - Associated workspace: (ваш workspace)
   - Capabilities: ✅ Read content, ✅ Update content
4. Нажмите **Submit**
5. **Скопируйте Internal Integration Token** (начинается с `secret_...`)

### 2.2 Создание базы данных

1. Создайте новую страницу в Notion
2. Добавьте Database (Table):
   - Название: `Конкуренты`
   
3. Настройте колонки:

| Название колонки | Тип | Обязательно | Описание |
|-----------------|-----|-------------|----------|
| **Название** | Title | ✅ | Название конкурента или товара |
| **URL конкурента** | URL | ✅ | Ссылка на страницу товара |
| **Последняя цена** | Number | ❌ | Последняя проверенная цена |
| **Последний статус** | Text | ❌ | Результат AI анализа |
| **Дата проверки** | Date | ❌ | Дата последней проверки |

4. **Подключите Integration к базе:**
   - Откройте меню базы (⋯ справа вверху)
   - **Connections** → **Connect to** → выберите `Competitor Price Scraper`

### 2.3 Получение Database ID

1. Откройте базу данных в Notion
2. Скопируйте URL из браузера:
   ```
   https://www.notion.so/workspace/abc123def456?v=...
                                    ^^^^^^^^^^^^
                                    Database ID
   ```
3. Database ID - это часть между последним `/` и `?v=`

### 2.4 Добавление тестовых данных

Добавьте несколько конкурентов для тестирования:

| Название | URL конкурента |
|----------|----------------|
| Конкурент А - Товар 1 | `https://example.com/product-1` |
| Конкурент Б - Товар 2 | `https://example.com/product-2` |

---

## Шаг 3: Настройка Telegram (5 минут)

### 3.1 Создание бота

1. Откройте Telegram и найдите [@BotFather](https://t.me/BotFather)
2. Отправьте команду: `/newbot`
3. Введите имя бота: `Competitor Price Monitor`
4. Введите username: `competitor_price_bot` (должен быть уникальным)
5. **Скопируйте Bot Token** (формат: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 3.2 Создание канала/группы для уведомлений

**Вариант А: Приватный канал (рекомендуется)**
1. Создайте новый канал в Telegram
2. Название: `Price Monitor Alerts`
3. Сделайте канал приватным
4. Добавьте бота как администратора канала

**Вариант Б: Группа**
1. Создайте новую группу
2. Добавьте бота в группу

### 3.3 Получение Chat ID

1. Отправьте любое сообщение в канал/группу
2. Откройте в браузере (замените `<BOT_TOKEN>` на ваш токен):
   ```
   https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
   ```
3. Найдите в JSON ответе:
   ```json
   "chat": {
     "id": -1001234567890,  ← Это ваш Chat ID
     ...
   }
   ```
4. **Важно:** Для групп и каналов ID начинается с `-`

---

## Шаг 4: Получение AI API Keys (5 минут)

### 4.1 Anthropic (Claude)

1. Перейдите на [https://console.anthropic.com/](https://console.anthropic.com/)
2. Sign up или Login
3. Перейдите в **API Keys**
4. Нажмите **Create Key**
5. Скопируйте API key (начинается с `sk-ant-...`)

**Стоимость:** ~$0.003 за 1K токенов (Claude 3.5 Sonnet)

### 4.2 OpenAI (для векторизации)

1. Перейдите на [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Sign up или Login
3. Нажмите **Create new secret key**
4. Скопируйте API key (начинается с `sk-...`)

**Стоимость:** ~$0.0001 за 1K токенов (text-embedding-3-small)

---

## Шаг 5: Импорт воркфлоу в n8n (10 минут)

### 5.1 Импорт Workflow B (RAG API) - сначала!

1. Откройте n8n
2. **Workflows** → **Add Workflow** → **Import from File**
3. Выберите файл: `workflow-b-competitor-price-scraper-rag-api.json`
4. Нажмите **Import**

### 5.2 Настройка Credentials в Workflow B

#### Anthropic
1. Кликните на ноду **Chat Model Anthropic**
2. **Credential to connect with** → **Create New**
3. Вставьте API key
4. Нажмите **Save**

#### OpenAI
1. Кликните на ноду **Embeddings OpenAI**
2. **Credential to connect with** → **Create New**
3. Вставьте API key
4. Нажмите **Save**

#### Supabase
1. Кликните на ноду **Supabase Vector Store**
2. **Credential to connect with** → **Create New**
3. Заполните:
   - Host: `https://abcdefgh.supabase.co` (ваш Project URL)
   - Service Role Secret: `eyJ...` (ваш Service Role Key)
4. Нажмите **Save**

### 5.3 Активация Workflow B

1. Нажмите **Active** toggle (справа вверху)
2. Откройте ноду **Webhook Trigger**
3. Скопируйте **Production Webhook URL**
4. Сохраните этот URL - он понадобится для Workflow A

Пример URL:
```
https://your-n8n-instance.com/webhook/rag-analysis
```

### 5.4 Импорт Workflow A (Main)

1. **Workflows** → **Add Workflow** → **Import from File**
2. Выберите файл: `workflow-a-competitor-price-scraper-main.json`
3. Нажмите **Import**

### 5.5 Настройка Credentials в Workflow A

#### Notion
1. Кликните на любую ноду **Notion**
2. **Credential to connect with** → **Create New**
3. Вставьте Integration Token (из Шага 2.1)
4. Нажмите **Save**

#### Telegram
1. Кликните на любую ноду **Telegram**
2. **Credential to connect with** → **Create New**
3. Вставьте Bot Token (из Шага 3.1)
4. Нажмите **Save**

---

## Шаг 6: Настройка переменных окружения (10 минут)

### 6.1 В n8n UI

1. Перейдите в **Settings** → **Environments**
2. Добавьте переменные (кнопка **Add Variable**):

```
DUMMY_TELEGRAM_CHAT_ID = -1001234567890
DUMMY_NOTION_DB_ID = abc123def456ghi789jkl012mno345pq
DUMMY_WEBHOOK_B_URL = https://your-n8n-instance.com/webhook/rag-analysis
DUMMY_CSS_SELECTOR_PRICE = .price
DUMMY_CSS_SELECTOR_DESCRIPTION = .description
```

### 6.2 Определение CSS селекторов

Для каждого конкурента:

1. Откройте страницу товара в браузере
2. Нажмите **F12** (DevTools)
3. Нажмите **Inspector** (иконка курсора)
4. Наведите на цену и кликните
5. В DevTools:
   - ПКМ на выделенном элементе
   - **Copy** → **Copy selector**
6. Вставьте в переменную `DUMMY_CSS_SELECTOR_PRICE`

Повторите для описания товара.

**Примеры:**
```css
.price                    /* Простой класс */
#product-price            /* ID элемента */
[data-price]              /* Атрибут */
.product .price-box span  /* Вложенный элемент */
```

**Для нескольких вариантов (fallback):**
```css
.price, .product-price, [data-price]
```

---

## Шаг 7: Тестирование (10 минут)

### 7.1 Тест Workflow B

1. Откройте Workflow B
2. Нажмите **Test Workflow**
3. В ноде **Webhook Trigger** нажмите **Listen for Test Event**
4. Отправьте тестовый POST запрос (можно через Postman):
   ```json
   POST https://your-n8n-instance.com/webhook-test/rag-analysis
   
   {
     "title": "Тестовый товар",
     "url": "https://example.com",
     "newPrice": 1500,
     "previousPrice": 1200,
     "newDescription": "Новое описание",
     "previousStatus": "Старый статус",
     "priceDifference": 300,
     "percentageChange": "25.00"
   }
   ```
5. Проверьте, что все ноды выполнились успешно
6. Проверьте в Supabase: Table Editor → competitor_prices (должна появиться запись)

### 7.2 Тест Workflow A

1. Убедитесь, что в Notion есть хотя бы один конкурент
2. Откройте Workflow A
3. Нажмите **Execute Workflow**
4. Дождитесь выполнения всех нод
5. Проверьте:
   - ✅ Telegram получил уведомление о старте
   - ✅ Данные извлечены из HTML
   - ✅ RAG Agent вернул анализ
   - ✅ Notion обновлен
   - ✅ Telegram получил финальный отчет (если были изменения)

### 7.3 Проверка ошибок

Если что-то не работает:

1. Откройте **Executions** в n8n
2. Найдите последнее выполнение
3. Откройте ноду, которая завершилась с ошибкой
4. Прочитайте сообщение об ошибке
5. Проверьте соответствующий раздел в README-n8n-workflows.md → Troubleshooting

---

## Шаг 8: Активация автоматического запуска

### 8.1 Проверка расписания

1. Откройте Workflow A
2. Кликните на **Cron Trigger (Daily 10:00)**
3. Проверьте Cron expression: `0 10 * * *`
   - Означает: каждый день в 10:00

**Для изменения расписания:**
```
0 10 * * *   → Ежедневно в 10:00
0 */6 * * *  → Каждые 6 часов
0 9,17 * * * → В 9:00 и 17:00
0 0 * * 1    → Каждый понедельник в 00:00
```

### 8.2 Активация

1. Нажмите **Active** toggle в Workflow A
2. Воркфлоу теперь будет запускаться автоматически

---

## Шаг 9: Мониторинг и оптимизация

### 9.1 Первая неделя

- Проверяйте Telegram каждый день
- Анализируйте точность парсинга цен
- Корректируйте CSS селекторы при необходимости
- Проверяйте качество AI-анализа

### 9.2 Настройка порога изменений

Если получаете слишком много уведомлений:

1. Откройте Workflow B
2. Найдите ноду **RAG Agent**
3. Измените в System Message:
   ```
   Если изменение цены меньше ±5%  → измените на ±10%
   ```

### 9.3 Мониторинг затрат

Отслеживайте расходы на API:
- **Anthropic Console**: [https://console.anthropic.com/settings/cost](https://console.anthropic.com/settings/cost)
- **OpenAI Usage**: [https://platform.openai.com/usage](https://platform.openai.com/usage)

**Примерные затраты:**
- 10 конкурентов × 1 проверка/день = ~$0.10/месяц

---

## ✅ Финальный чеклист

- [ ] Supabase проект создан и таблица настроена
- [ ] Notion база данных создана и подключена
- [ ] Telegram бот создан и Chat ID получен
- [ ] API keys получены (Anthropic, OpenAI)
- [ ] Workflow B импортирован и активирован
- [ ] Workflow A импортирован и активирован
- [ ] Все credentials настроены в n8n
- [ ] Переменные окружения заполнены
- [ ] CSS селекторы определены для каждого сайта
- [ ] Тестовый запуск выполнен успешно
- [ ] Получено первое уведомление в Telegram
- [ ] Автоматическое расписание активировано

---

## 🎉 Готово!

Ваш интеллектуальный агент мониторинга цен конкурентов настроен и готов к работе!

**Следующие шаги:**
1. Добавьте больше конкурентов в Notion
2. Настройте уникальные CSS селекторы для каждого сайта
3. Мониторьте первые отчеты и корректируйте настройки
4. Наслаждайтесь автоматическим мониторингом! 🚀

---

## 📞 Нужна помощь?

- Проверьте раздел **Troubleshooting** в README-n8n-workflows.md
- Изучите логи выполнения в n8n (Executions)
- Проверьте документацию n8n: [https://docs.n8n.io](https://docs.n8n.io)