# Workflow Diagrams

## 🔄 RSS Processing Flow

```mermaid
flowchart TD
    Start([Schedule Trigger<br/>Every 3 hours]) --> RSS[RSS Read<br/>TechCrunch AI Feed]
    RSS --> Loop{Loop Over Items<br/>Batch: 1}
    Loop --> Wait[Wait 5 seconds]
    Wait --> Check[Supabase: Check URL<br/>processed_urls table]
    Check --> IF1{URL processed?<br/>len == 0?}
    
    IF1 -->|No, skip| Loop
    IF1 -->|Yes, new| SetVars[Set Variables<br/>url_site, title, api_key]
    
    SetVars --> Firecrawl1[Firecrawl: Scrape Page<br/>markdown + screenshot]
    
    Firecrawl1 --> Extract[Extract Contacts<br/>emails, phones, social]
    Firecrawl1 --> Screenshot[Get Screenshot<br/>as image file]
    
    Extract --> Format[Format Post<br/>HTML with emojis]
    Format --> Merge[Merge Data<br/>text + image]
    Screenshot --> Merge
    
    Merge --> TG1[Send to Telegram<br/>sendPhoto with caption]
    TG1 --> Save1[Supabase: Save URL<br/>with post_text]
    Save1 --> Continue[Continue Loop]
    Continue --> Loop
```

## 📱 Visa Query Flow

```mermaid
flowchart TD
    Webhook([Telegram Webhook<br/>POST /telegram]) --> Parse[Parse Command<br/>Extract /visa params]
    Parse --> IF1{Is /visa<br/>command?}
    
    IF1 -->|No| Stop1[Stop: Not visa]
    IF1 -->|Yes| IF2{Has query<br/>params?}
    
    IF2 -->|No| Hint[Send Format Hint<br/>/visa country city]
    IF2 -->|Yes| BuildQuery[Build Search Query<br/>посольство OR визовый центр...]
    
    BuildQuery --> Search[Firecrawl: Search<br/>limit: 5 results]
    Search --> Rank[Rank URLs<br/>by relevance score]
    Rank --> IF3{URL found?}
    
    IF3 -->|No| NotFound[Send: Not Found<br/>❌ message]
    IF3 -->|Yes| Scrape[Firecrawl: Scrape<br/>Embassy page]
    
    Scrape --> CheckSlots[Check Slots<br/>regex keywords]
    CheckSlots --> FormatMsg[Format Message<br/>status + contacts]
    FormatMsg --> SendResult[Send Result<br/>to Telegram]
    SendResult --> SaveQuery[Supabase: Save<br/>visa_queries]
```

## 🏗️ Complete System Architecture

```mermaid
graph TB
    subgraph "External Sources"
        RSS_Feed[📰 RSS Feed<br/>TechCrunch]
        TG_Users[👥 Telegram Users]
    end
    
    subgraph "n8n Workflows"
        RSS_WF[🔄 RSS Workflow]
        Visa_WF[📱 Visa Workflow]
    end
    
    subgraph "Services"
        Firecrawl[🔥 Firecrawl API<br/>Scraping & Search]
        TG_API[💬 Telegram API<br/>Bot Messages]
        Supabase[🗄️ Supabase<br/>Database]
    end
    
    subgraph "Outputs"
        TG_Channel[📢 Telegram Channel<br/>RSS Posts]
        TG_Chat[💬 User Chats<br/>Visa Info]
    end
    
    RSS_Feed -->|Every 3h| RSS_WF
    TG_Users -->|/visa command| Visa_WF
    
    RSS_WF <-->|Scrape| Firecrawl
    Visa_WF <-->|Search & Scrape| Firecrawl
    
    RSS_WF -->|Check duplicates| Supabase
    RSS_WF -->|Save processed| Supabase
    Visa_WF -->|Save queries| Supabase
    
    RSS_WF -->|sendPhoto| TG_API
    Visa_WF -->|sendMessage| TG_API
    
    TG_API -->|Posts| TG_Channel
    TG_API -->|Responses| TG_Chat
```

## 🔐 Data Flow - RSS

```mermaid
sequenceDiagram
    participant Scheduler
    participant RSS
    participant Firecrawl
    participant Parser
    participant Supabase
    participant Telegram
    
    Scheduler->>RSS: Trigger every 3h
    RSS->>RSS: Fetch feed items
    
    loop For each item
        RSS->>Supabase: Check if URL exists
        Supabase-->>RSS: Return results
        
        alt URL not processed
            RSS->>Firecrawl: Scrape page (markdown + screenshot)
            Firecrawl-->>Parser: Return data
            Parser->>Parser: Extract contacts (regex)
            Parser->>Parser: Format HTML post
            Parser->>Telegram: Send photo with caption
            Parser->>Supabase: Save processed URL
        else URL already processed
            RSS->>RSS: Skip to next
        end
    end
```

## 🌍 Data Flow - Visa

```mermaid
sequenceDiagram
    participant User
    participant Telegram
    participant Webhook
    participant Firecrawl
    participant Analyzer
    participant Supabase
    
    User->>Telegram: /visa Poland Tashkent
    Telegram->>Webhook: POST webhook
    Webhook->>Webhook: Parse command
    
    alt Valid query
        Webhook->>Firecrawl: Search for embassy
        Firecrawl-->>Webhook: Return search results
        Webhook->>Webhook: Rank URLs by score
        
        alt URL found
            Webhook->>Firecrawl: Scrape embassy page
            Firecrawl-->>Analyzer: Return markdown
            Analyzer->>Analyzer: Check slots (regex)
            Analyzer->>Analyzer: Extract contacts
            Analyzer->>Telegram: Send formatted result
            Analyzer->>Supabase: Save query
            Telegram-->>User: Result message
        else URL not found
            Webhook->>Telegram: Send not found
            Telegram-->>User: ❌ Not found
        end
    else Invalid query
        Webhook->>Telegram: Send format hint
        Telegram-->>User: Format example
    end
```

## 📊 Database Schema

```mermaid
erDiagram
    processed_urls {
        bigserial id PK
        text url UK "Unique URL"
        timestamp processed_at "When processed"
        text post_text "Generated post"
        timestamp created_at
    }
    
    visa_queries {
        bigserial id PK
        text chat_id "Telegram chat ID"
        text query "User query"
        text found_url "Found embassy URL"
        boolean has_slots "Slots available?"
        timestamp queried_at "When queried"
        timestamp created_at
    }
    
    processed_urls ||--o{ processed_urls : "references self for dedup"
    visa_queries ||--o{ visa_queries : "references self for history"
```

## 🎯 Node Connections Map

### RSS Workflow Nodes:
1. `Запуск по расписанию (RSS)` → `RSS Read`
2. `RSS Read` → `Loop Over Items`
3. `Loop Over Items` → `Wait`
4. `Wait` → `Supabase: Проверка обработанных`
5. `Supabase: Проверка обработанных` → `Если не обработан (len==0)`
6. `Если не обработан (len==0)` → TRUE → `Установка переменных`
7. `Если не обработан (len==0)` → FALSE → `Loop Over Items` (skip)
8. `Установка переменных` → `Firecrawl: Парсинг страницы`
9. `Firecrawl: Парсинг страницы` → `Извлечение контактов` & `Получить скриншот`
10. `Извлечение контактов` → `Создать пост (Форматирование)`
11. `Создать пост (Форматирование)` → `Объединение данных` (input 0)
12. `Получить скриншот` → `Объединение данных` (input 1)
13. `Объединение данных` → `Отправить в Telegram (RSS)`
14. `Отправить в Telegram (RSS)` → `Supabase: Сохранить обработанный`
15. `Supabase: Сохранить обработанный` → `Continue Loop`
16. `Continue Loop` → `Loop Over Items`

### Visa Workflow Nodes:
1. `Webhook /telegram` → `Определить команду /visa`
2. `Определить команду /visa` → `IF: не /visa → стоп`
3. `IF: не /visa → стоп` → TRUE → `Стоп: не /visa`
4. `IF: не /visa → стоп` → FALSE → `IF: есть query?`
5. `IF: есть query?` → FALSE → `Подсказка формата`
6. `IF: есть query?` → TRUE → `Сформировать поисковый запрос`
7. `Сформировать поисковый запрос` → `Firecrawl: Поиск посольств`
8. `Firecrawl: Поиск посольств` → `Выбрать лучший URL`
9. `Выбрать лучший URL` → `IF: найден URL?`
10. `IF: найден URL?` → FALSE → `Отправить: не найдено`
11. `IF: найден URL?` → TRUE → `Firecrawl: Страница посольства`
12. `Firecrawl: Страница посольства` → `Проверка наличия слотов`
13. `Проверка наличия слотов` → `Форматировать сообщение о визе`
14. `Форматировать сообщение о визе` → `Отправить результат о визе`
15. `Отправить результат о визе` → `Supabase: Сохранить запрос визы`

## 🔄 State Machine - Visa Query

```mermaid
stateDiagram-v2
    [*] --> Received: Webhook receives message
    Received --> ParseCommand: Extract text
    
    ParseCommand --> NotVisa: Not /visa command
    ParseCommand --> CheckQuery: Is /visa
    
    NotVisa --> [*]: Stop processing
    
    CheckQuery --> NoQuery: Empty query
    CheckQuery --> Search: Valid query
    
    NoQuery --> SendHint: Send format help
    SendHint --> [*]
    
    Search --> Ranking: Firecrawl search
    Ranking --> NoURL: No results
    Ranking --> Scrape: URL found
    
    NoURL --> SendNotFound: Notify user
    SendNotFound --> [*]
    
    Scrape --> CheckSlots: Parse content
    CheckSlots --> Format: Analyze
    Format --> Send: Create message
    Send --> Save: Send to Telegram
    Save --> [*]: Save to DB
```

## 📈 Performance Metrics

```mermaid
gantt
    title RSS Workflow Timeline (per item)
    dateFormat  s
    
    section Processing
    Wait (rate limit)           :0, 5s
    Supabase check             :5s, 1s
    Firecrawl scrape           :6s, 8s
    Extract contacts           :14s, 1s
    Format post                :15s, 1s
    Get screenshot             :6s, 3s
    Merge data                 :16s, 1s
    Send Telegram              :17s, 2s
    Save to Supabase           :19s, 1s
    
    section Total
    Total time per item        :0, 20s
```

## 🔍 Decision Tree - URL Ranking

```mermaid
graph TD
    URL[URL from Search] --> Score{Calculate Score}
    
    Score --> Check1{Contains .uz?}
    Check1 -->|Yes| Add3_1[+3 points]
    Check1 -->|No| Check2
    
    Check2{Contains vfsglobal?}
    Check2 -->|Yes| Add3_2[+3 points]
    Check2 -->|No| Check3
    
    Check3{Contains visametric?}
    Check3 -->|Yes| Add3_3[+3 points]
    Check3 -->|No| Check4
    
    Check4{Contains embassy/mfa?}
    Check4 -->|Yes| Add2_1[+2 points]
    Check4 -->|No| Check5
    
    Check5{Contains consulate?}
    Check5 -->|Yes| Add2_2[+2 points]
    Check5 -->|No| Done
    
    Add3_1 --> Check2
    Add3_2 --> Check3
    Add3_3 --> Check4
    Add2_1 --> Check5
    Add2_2 --> Done[Calculate Total]
    Done --> Sort[Sort by Score DESC]
    Sort --> Select[Select Top URL]
```

---

## 📝 Legend

- 🔄 = Scheduled/Automated process
- 📱 = User-triggered process
- 🔥 = External API call (Firecrawl)
- 💬 = Telegram interaction
- 🗄️ = Database operation
- ✅ = Success path
- ❌ = Error/failure path
- 🔍 = Decision point
- 📊 = Data processing

---

**Note:** All diagrams are in Mermaid format and can be rendered in GitHub, GitLab, or any Markdown viewer that supports Mermaid.
