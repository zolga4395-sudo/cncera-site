# Changelog

## Version 1.0.0 - Complete Implementation (2025-10-09)

### ✨ Features

#### RSS Workflow
- ✅ **Scheduled RSS Monitoring** - автоматическая проверка каждые 3 часа
- ✅ **Smart Deduplication** - проверка обработанных URL в Supabase
- ✅ **Advanced Contact Extraction** - regex для emails, телефонов, соцсетей
- ✅ **Screenshot Capture** - визуальное представление статей
- ✅ **HTML Formatting** - красивое форматирование с эмодзи
- ✅ **Telegram Integration** - автопубликация в канал
- ✅ **Rate Limiting** - задержка 5 секунд между элементами

#### Visa Workflow
- ✅ **Telegram Bot Interface** - обработка команд `/visa`
- ✅ **Intelligent Search** - поиск посольств через Firecrawl
- ✅ **URL Ranking** - ранжирование результатов по релевантности
- ✅ **Slot Detection** - автоматическая проверка доступности записи
- ✅ **Contact Extraction** - извлечение emails и телефонов
- ✅ **Formatted Responses** - понятные ответы с эмодзи
- ✅ **Query History** - сохранение всех запросов в Supabase

### 🔧 Technical Implementation

#### Nodes Completed (RSS)
1. Запуск по расписанию (RSS) - Schedule Trigger
2. RSS Read - RSS Feed Reader
3. Loop Over Items - Split in Batches
4. Wait - Delay between items
5. Supabase: Проверка обработанных - Check processed URLs
6. Если не обработан (len==0) - Deduplication IF
7. Установка переменных - Set variables
8. Firecrawl: Парсинг страницы - Page scraping
9. Извлечение контактов - Contact extraction (Code)
10. Создать пост (Форматирование) - Post formatting (Code)
11. Получить скриншот - Screenshot download
12. Объединение данных - Merge data
13. Отправить в Telegram (RSS) - Send to channel
14. Supabase: Сохранить обработанный - Save processed URL
15. Continue Loop - Loop continuation

#### Nodes Completed (Visa)
1. Webhook /telegram - Telegram webhook receiver
2. Определить команду /visa - Command parser (Code)
3. IF: не /visa → стоп - Command validation
4. Подсказка формата - Format hint message
5. IF: есть query? - Query validation
6. Сформировать поисковый запрос - Build search query
7. Firecrawl: Поиск посольств - Embassy search
8. Выбрать лучший URL - URL ranking (Code)
9. IF: найден URL? - URL validation
10. Firecrawl: Страница посольства - Embassy page scraping
11. Проверка наличия слотов - Slot detection (Code)
12. Форматировать сообщение о визе - Format visa message (Code)
13. Отправить результат о визе - Send visa result
14. Supabase: Сохранить запрос визы - Save query
15. Отправить: не найдено - Not found message
16. Стоп: не /visa - Stop non-visa commands

### 🗄️ Database Schema

#### Tables
- `processed_urls` - RSS URL deduplication
  - Fields: id, url (unique), processed_at, post_text, created_at
  - Indexes: url, processed_at
  
- `visa_queries` - Visa query history
  - Fields: id, chat_id, query, found_url, has_slots, queried_at, created_at
  - Indexes: chat_id, query, queried_at, has_slots

#### Views
- `recent_visa_queries` - Recent visa queries with grouping
- `popular_visa_queries` - Most popular queries
- `rss_stats` - RSS processing statistics

#### Functions
- `cleanup_old_processed_urls()` - Cleanup URLs older than 30 days
- `cleanup_old_visa_queries()` - Cleanup queries older than 90 days

### 🔗 Connections & Flow

#### RSS Flow
```
Schedule → RSS → Loop → Wait → Check → IF → 
Set Vars → Scrape → Extract & Screenshot → 
Merge → Telegram → Save → Loop
```

#### Visa Flow
```
Webhook → Parse → IF (visa?) → IF (query?) → 
Search → Rank → IF (found?) → Scrape → 
Check Slots → Format → Send → Save
```

### 📚 Documentation

#### Created Files
1. **combined_workflow.json** - Complete n8n workflow (ready to import)
2. **README.md** - Quick start guide
3. **WORKFLOW_DOCUMENTATION.md** - Detailed technical documentation
4. **WORKFLOW_DIAGRAM.md** - Mermaid diagrams and visualizations
5. **SETUP_GUIDE.md** - Step-by-step setup instructions
6. **supabase_setup.sql** - Database schema and setup
7. **.env.example** - Environment variables template
8. **CHANGELOG.md** - This file

### 🎨 Features Details

#### Contact Extraction (RSS)
- **Emails**: Full regex matching (RFC-compliant)
- **Phones**: International format support (+XXX XXX XXX)
- **Social Media**:
  - Telegram: @username or t.me/username
  - WhatsApp: wa.me/number
  - Instagram: instagram.com/username
  - Facebook: facebook.com/username
  - LinkedIn: linkedin.com/in/username
- **Deduplication**: Automatic removal of duplicates

#### URL Ranking (Visa)
- **.uz domain**: +3 points (local sites)
- **vfsglobal**: +3 points (visa service)
- **visametric**: +3 points (visa service)
- **embassy/mfa**: +2 points (official)
- **consulate**: +2 points (official)

#### Slot Detection Keywords
- English: appointment, book, signup, enroll, next date, available, open slot
- Russian: запись, доступн, свободн

### 🔐 Security Features

- ✅ API key separation (anon vs service_role)
- ✅ Environment variables support
- ✅ RLS ready (optional)
- ✅ HTTPS webhook requirement
- ✅ No sensitive data in responses

### ⚡ Performance Optimizations

- ✅ Batch processing (1 item at a time)
- ✅ Rate limiting (5s delay)
- ✅ Timeout configuration
- ✅ Indexed database queries
- ✅ Efficient regex patterns
- ✅ Screenshot caching

### 🐛 Error Handling

- ✅ `alwaysOutputData: true` on critical nodes
- ✅ `onError: continueRegularOutput` for resilience
- ✅ Validation IFs for data integrity
- ✅ Fallback messages for errors
- ✅ Comprehensive logging

### 📊 Metrics & Analytics

#### Available Metrics
- Total processed URLs
- Processing rate per day
- Popular visa queries
- Slot availability tracking
- Response times
- Error rates

#### Monitoring Capabilities
- n8n Executions dashboard
- Supabase Analytics
- Custom SQL views
- Telegram delivery status

### 🌍 Localization

- ✅ Russian language UI
- ✅ Cyrillic support in search
- ✅ Russian keywords for slot detection
- ✅ HTML formatting with emojis

### 🚀 Future Enhancements (Roadmap)

#### Planned Features
- [ ] Multiple RSS sources support
- [ ] Notification when slots appear
- [ ] Multi-language support
- [ ] Advanced analytics dashboard
- [ ] User subscription management
- [ ] Scheduled visa checks
- [ ] Price comparison
- [ ] Document requirements info

#### Technical Improvements
- [ ] Redis caching layer
- [ ] GraphQL API
- [ ] WebSocket for real-time updates
- [ ] Machine learning for better slot detection
- [ ] OCR for screenshot analysis

### 📝 Notes

#### API Limits
- **Firecrawl Free Tier**: ~500 requests/month
- **Telegram Bot API**: 30 messages/second
- **Supabase Free Tier**: 500MB database, 2GB bandwidth

#### Known Limitations
1. Slot detection based on keywords (may have false positives)
2. RSS limited to single source (configurable)
3. No authentication for visa queries (public bot)
4. Screenshot size not optimized

#### Breaking Changes
None - initial release

### 🙏 Credits

- **n8n**: Workflow automation platform
- **Firecrawl**: Web scraping API
- **Supabase**: Database and backend
- **Telegram**: Messaging platform

### 📄 License

MIT License - Free to use and modify

---

## Migration Guide

N/A - Initial release

---

## Support

For issues and questions:
- Check SETUP_GUIDE.md
- Review WORKFLOW_DOCUMENTATION.md
- Check n8n Executions for errors
- Review Supabase logs

---

**Version**: 1.0.0  
**Date**: 2025-10-09  
**Status**: ✅ Production Ready
