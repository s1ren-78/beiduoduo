-- Beiduoduo report mirror schema (SQLite)

CREATE TABLE IF NOT EXISTS report_source_file (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_type TEXT NOT NULL CHECK (source_type IN ('local', 'feishu', 'unsupported')),
  source_id TEXT NOT NULL,
  file_path TEXT,
  file_name TEXT,
  file_ext TEXT,
  category TEXT,
  file_size INTEGER,
  file_mtime TEXT,
  content_hash TEXT,
  is_supported INTEGER NOT NULL DEFAULT 1,
  unsupported_reason TEXT,
  meta TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(source_type, source_id)
);

CREATE TABLE IF NOT EXISTS report_document (
  doc_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
  source_type TEXT NOT NULL CHECK (source_type IN ('local', 'feishu')),
  source_id TEXT NOT NULL,
  title TEXT,
  category TEXT,
  source_file_id INTEGER REFERENCES report_source_file(id) ON DELETE SET NULL,
  full_text TEXT NOT NULL DEFAULT '',
  content_hash TEXT NOT NULL,
  updated_time TEXT,
  synced_at TEXT NOT NULL DEFAULT (datetime('now')),
  meta TEXT NOT NULL DEFAULT '{}',
  UNIQUE(source_type, source_id)
);

CREATE TABLE IF NOT EXISTS report_chunk (
  chunk_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
  doc_id TEXT NOT NULL REFERENCES report_document(doc_id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  section TEXT,
  content TEXT NOT NULL,
  start_offset INTEGER NOT NULL DEFAULT 0,
  end_offset INTEGER NOT NULL DEFAULT 0,
  updated_time TEXT,
  meta TEXT NOT NULL DEFAULT '{}',
  UNIQUE(doc_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS report_sync_run (
  run_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
  scope TEXT NOT NULL CHECK (scope IN ('local', 'feishu', 'all', 'market', 'financials')),
  mode TEXT NOT NULL CHECK (mode IN ('full', 'incremental')),
  reason TEXT NOT NULL CHECK (reason IN ('manual', 'schedule', 'miss')),
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'success', 'failed')),
  started_at TEXT,
  ended_at TEXT,
  stats TEXT NOT NULL DEFAULT '{}',
  error_text TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS report_checkpoint (
  checkpoint_key TEXT PRIMARY KEY,
  cursor TEXT,
  watermark_ts TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  meta TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS report_whitelist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_type TEXT NOT NULL CHECK (entry_type IN ('space', 'folder', 'doc', 'drive_file')),
  entry_token TEXT NOT NULL UNIQUE,
  label TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  meta TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- FTS5 virtual table for full-text search on chunks
CREATE VIRTUAL TABLE IF NOT EXISTS report_chunk_fts USING fts5(
  chunk_id UNINDEXED,
  doc_id UNINDEXED,
  content,
  tokenize='trigram'
);

-- ── Market & On-chain Data Tables ──

CREATE TABLE IF NOT EXISTS market_watchlist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  asset_class TEXT NOT NULL CHECK (asset_class IN ('stock', 'crypto', 'protocol', 'chain')),
  label TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  meta TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(symbol, asset_class)
);

CREATE TABLE IF NOT EXISTS market_price_daily (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  asset_class TEXT NOT NULL CHECK (asset_class IN ('stock', 'crypto')),
  trade_date TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume REAL,
  market_cap REAL,
  meta TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(symbol, asset_class, trade_date)
);

CREATE TABLE IF NOT EXISTS market_quote_latest (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  asset_class TEXT NOT NULL CHECK (asset_class IN ('stock', 'crypto')),
  price REAL,
  change_pct REAL,
  volume REAL,
  market_cap REAL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  meta TEXT NOT NULL DEFAULT '{}',
  UNIQUE(symbol, asset_class)
);

CREATE TABLE IF NOT EXISTS fin_statement (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id TEXT NOT NULL,
  entity_type TEXT NOT NULL CHECK (entity_type IN ('stock', 'protocol')),
  period TEXT NOT NULL,
  period_type TEXT NOT NULL CHECK (period_type IN ('quarterly', 'annual', 'monthly', 'weekly')),
  metric TEXT NOT NULL,
  value REAL,
  unit TEXT,
  meta TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(entity_id, entity_type, period, metric)
);

CREATE TABLE IF NOT EXISTS onchain_protocol_daily (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  protocol TEXT NOT NULL,
  metric_date TEXT NOT NULL,
  tvl REAL,
  revenue REAL,
  fees REAL,
  active_users INTEGER,
  transactions INTEGER,
  meta TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(protocol, metric_date)
);

CREATE TABLE IF NOT EXISTS onchain_chain_daily (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chain TEXT NOT NULL,
  metric_date TEXT NOT NULL,
  gas_used REAL,
  tps REAL,
  active_addresses INTEGER,
  transaction_count INTEGER,
  tvl REAL,
  meta TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(chain, metric_date)
);

CREATE TABLE IF NOT EXISTS onchain_token_liquidity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token TEXT NOT NULL,
  chain TEXT NOT NULL,
  metric_date TEXT NOT NULL,
  pool_count INTEGER,
  total_liquidity_usd REAL,
  volume_24h REAL,
  meta TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(token, chain, metric_date)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_report_source_category ON report_source_file(category);
CREATE INDEX IF NOT EXISTS idx_report_source_hash ON report_source_file(content_hash);
CREATE INDEX IF NOT EXISTS idx_report_doc_source ON report_document(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_report_doc_updated_time ON report_document(updated_time);
CREATE INDEX IF NOT EXISTS idx_report_chunk_doc ON report_chunk(doc_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_report_sync_run_status_time ON report_sync_run(status, created_at);
CREATE INDEX IF NOT EXISTS idx_report_whitelist_enabled ON report_whitelist(enabled, entry_type);

CREATE TABLE IF NOT EXISTS kol_watchlist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id TEXT NOT NULL DEFAULT '',
  kol_id TEXT NOT NULL,
  name TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  search_queries TEXT NOT NULL DEFAULT '[]',
  enabled INTEGER NOT NULL DEFAULT 1,
  meta TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(owner_id, kol_id)
);

CREATE INDEX IF NOT EXISTS idx_market_watchlist_enabled ON market_watchlist(enabled, asset_class);
CREATE INDEX IF NOT EXISTS idx_kol_watchlist_enabled ON kol_watchlist(enabled, category);
CREATE INDEX IF NOT EXISTS idx_kol_watchlist_owner ON kol_watchlist(owner_id, enabled);
CREATE INDEX IF NOT EXISTS idx_market_price_daily_symbol ON market_price_daily(symbol, asset_class, trade_date);
CREATE INDEX IF NOT EXISTS idx_market_quote_latest_symbol ON market_quote_latest(symbol, asset_class);
CREATE INDEX IF NOT EXISTS idx_fin_statement_entity ON fin_statement(entity_id, entity_type, period);
CREATE INDEX IF NOT EXISTS idx_onchain_protocol_daily ON onchain_protocol_daily(protocol, metric_date);
CREATE INDEX IF NOT EXISTS idx_onchain_chain_daily ON onchain_chain_daily(chain, metric_date);
CREATE INDEX IF NOT EXISTS idx_onchain_token_liquidity ON onchain_token_liquidity(token, chain, metric_date);

-- ── Structured Report Enrichment Tables ──

-- Layer 1: 研报元数据增强
CREATE TABLE IF NOT EXISTS report_meta_enriched (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id TEXT NOT NULL UNIQUE REFERENCES report_document(doc_id) ON DELETE CASCADE,
  display_title TEXT,
  companies TEXT NOT NULL DEFAULT '[]',
  tickers TEXT NOT NULL DEFAULT '[]',
  sectors TEXT NOT NULL DEFAULT '[]',
  report_type TEXT,
  language TEXT,
  publish_date TEXT,
  author TEXT,
  source_org TEXT,
  quality_score INTEGER,
  summary TEXT,
  model_used TEXT NOT NULL,
  extracted_at TEXT NOT NULL DEFAULT (datetime('now')),
  meta TEXT NOT NULL DEFAULT '{}'
);

-- Layer 2: 投资论点
CREATE TABLE IF NOT EXISTS report_thesis (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id TEXT NOT NULL REFERENCES report_document(doc_id) ON DELETE CASCADE,
  company TEXT NOT NULL,
  ticker TEXT,
  direction TEXT NOT NULL CHECK (direction IN ('bullish','bearish','neutral')),
  confidence TEXT NOT NULL CHECK (confidence IN ('high','medium','low')),
  time_horizon TEXT CHECK (time_horizon IN ('short','medium','long')),
  thesis_text TEXT NOT NULL,
  key_catalysts TEXT NOT NULL DEFAULT '[]',
  key_risks TEXT NOT NULL DEFAULT '[]',
  model_used TEXT NOT NULL,
  extracted_at TEXT NOT NULL DEFAULT (datetime('now')),
  meta TEXT NOT NULL DEFAULT '{}',
  UNIQUE(doc_id, company)
);

-- Layer 3: 财务指标
CREATE TABLE IF NOT EXISTS report_metric (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id TEXT NOT NULL REFERENCES report_document(doc_id) ON DELETE CASCADE,
  company TEXT NOT NULL,
  ticker TEXT,
  period TEXT NOT NULL,
  metric TEXT NOT NULL,
  value REAL,
  unit TEXT,
  yoy_change REAL,
  context TEXT,
  model_used TEXT NOT NULL,
  extracted_at TEXT NOT NULL DEFAULT (datetime('now')),
  meta TEXT NOT NULL DEFAULT '{}',
  UNIQUE(doc_id, company, period, metric)
);

CREATE INDEX IF NOT EXISTS idx_report_meta_enriched_doc ON report_meta_enriched(doc_id);
CREATE INDEX IF NOT EXISTS idx_report_meta_enriched_type ON report_meta_enriched(report_type, extracted_at DESC);
CREATE INDEX IF NOT EXISTS idx_report_thesis_doc ON report_thesis(doc_id);
CREATE INDEX IF NOT EXISTS idx_report_thesis_company ON report_thesis(company, direction);
CREATE INDEX IF NOT EXISTS idx_report_thesis_direction_time ON report_thesis(direction, extracted_at DESC);
CREATE INDEX IF NOT EXISTS idx_report_metric_doc ON report_metric(doc_id);
CREATE INDEX IF NOT EXISTS idx_report_metric_company ON report_metric(company, metric);
CREATE INDEX IF NOT EXISTS idx_report_metric_extracted ON report_metric(extracted_at DESC);
