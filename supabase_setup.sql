-- Supabase Setup Script for RSS & Visa Monitor Workflow
-- Run this script in your Supabase SQL Editor

-- ============================================
-- TABLE: processed_urls
-- Stores processed RSS feed URLs to avoid duplicates
-- ============================================

CREATE TABLE IF NOT EXISTS processed_urls (
  id BIGSERIAL PRIMARY KEY,
  url TEXT UNIQUE NOT NULL,
  processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  post_text TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for faster URL lookups
CREATE INDEX IF NOT EXISTS idx_processed_urls_url ON processed_urls(url);
CREATE INDEX IF NOT EXISTS idx_processed_urls_processed_at ON processed_urls(processed_at DESC);

-- ============================================
-- TABLE: visa_queries
-- Stores visa query history and results
-- ============================================

CREATE TABLE IF NOT EXISTS visa_queries (
  id BIGSERIAL PRIMARY KEY,
  chat_id TEXT NOT NULL,
  query TEXT NOT NULL,
  found_url TEXT,
  has_slots BOOLEAN DEFAULT FALSE,
  queried_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for analytics
CREATE INDEX IF NOT EXISTS idx_visa_queries_chat_id ON visa_queries(chat_id);
CREATE INDEX IF NOT EXISTS idx_visa_queries_query ON visa_queries(query);
CREATE INDEX IF NOT EXISTS idx_visa_queries_queried_at ON visa_queries(queried_at DESC);
CREATE INDEX IF NOT EXISTS idx_visa_queries_has_slots ON visa_queries(has_slots) WHERE has_slots = true;

-- ============================================
-- OPTIONAL: Enable Row Level Security (RLS)
-- ============================================

-- Uncomment if you want to enable RLS
-- ALTER TABLE processed_urls ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE visa_queries ENABLE ROW LEVEL SECURITY;

-- Create policies for service_role (full access)
-- CREATE POLICY "Service role can do everything on processed_urls"
--   ON processed_urls
--   FOR ALL
--   TO service_role
--   USING (true)
--   WITH CHECK (true);

-- CREATE POLICY "Service role can do everything on visa_queries"
--   ON visa_queries
--   FOR ALL
--   TO service_role
--   USING (true)
--   WITH CHECK (true);

-- ============================================
-- HELPFUL VIEWS FOR ANALYTICS
-- ============================================

-- View: Recent visa queries
CREATE OR REPLACE VIEW recent_visa_queries AS
SELECT 
  query,
  found_url,
  has_slots,
  COUNT(*) as query_count,
  MAX(queried_at) as last_queried
FROM visa_queries
GROUP BY query, found_url, has_slots
ORDER BY last_queried DESC;

-- View: Popular queries
CREATE OR REPLACE VIEW popular_visa_queries AS
SELECT 
  query,
  COUNT(*) as total_queries,
  SUM(CASE WHEN has_slots THEN 1 ELSE 0 END) as times_with_slots,
  MAX(queried_at) as last_queried
FROM visa_queries
GROUP BY query
ORDER BY total_queries DESC;

-- View: RSS processing stats
CREATE OR REPLACE VIEW rss_stats AS
SELECT 
  COUNT(*) as total_processed,
  DATE(processed_at) as process_date,
  COUNT(DISTINCT url) as unique_urls
FROM processed_urls
GROUP BY DATE(processed_at)
ORDER BY process_date DESC;

-- ============================================
-- CLEANUP FUNCTIONS (OPTIONAL)
-- ============================================

-- Function to cleanup old processed URLs (older than 30 days)
CREATE OR REPLACE FUNCTION cleanup_old_processed_urls()
RETURNS INTEGER AS $$
DECLARE
  deleted_count INTEGER;
BEGIN
  DELETE FROM processed_urls 
  WHERE processed_at < NOW() - INTERVAL '30 days';
  
  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to cleanup old visa queries (older than 90 days)
CREATE OR REPLACE FUNCTION cleanup_old_visa_queries()
RETURNS INTEGER AS $$
DECLARE
  deleted_count INTEGER;
BEGIN
  DELETE FROM visa_queries 
  WHERE queried_at < NOW() - INTERVAL '90 days';
  
  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- VERIFICATION QUERIES
-- ============================================

-- Run these to verify the setup:

-- Check processed_urls table
-- SELECT COUNT(*) as total_urls FROM processed_urls;

-- Check visa_queries table
-- SELECT COUNT(*) as total_queries FROM visa_queries;

-- Check recent visa queries
-- SELECT * FROM recent_visa_queries LIMIT 10;

-- Check popular queries
-- SELECT * FROM popular_visa_queries LIMIT 10;

-- ============================================
-- NOTES
-- ============================================

/*
1. Make sure to set up proper API keys in Supabase:
   - Get your anon key from: Settings > API
   - Get your service_role key from: Settings > API (keep this secret!)

2. For production, enable RLS and create appropriate policies

3. Consider setting up scheduled cleanup jobs using pg_cron:
   SELECT cron.schedule('cleanup-old-urls', '0 3 * * *', 'SELECT cleanup_old_processed_urls()');
   SELECT cron.schedule('cleanup-old-queries', '0 4 * * *', 'SELECT cleanup_old_visa_queries()');

4. Monitor table sizes and indexes regularly:
   SELECT 
     schemaname,
     tablename,
     pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
   FROM pg_tables
   WHERE schemaname = 'public'
   ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
*/
