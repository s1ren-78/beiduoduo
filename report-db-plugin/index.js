import { Type } from "@sinclair/typebox";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";

function json(data) {
  return {
    content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
    details: data,
  };
}

function resolveConfig(api) {
  const cfg = api?.config?.plugins?.entries?.["openclaw-report-db"]?.config || {};
  const baseUrl = String(cfg.baseUrl || "http://127.0.0.1:8788").replace(/\/$/, "");
  const timeoutMs = Number(cfg.timeoutMs || 30000);
  return { baseUrl, timeoutMs };
}

async function request(api, path, options = {}) {
  const { baseUrl, timeoutMs } = resolveConfig(api);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      signal: controller.signal,
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      return { error: `HTTP ${resp.status}`, body };
    }
    return body;
  } catch (err) {
    return { error: String(err) };
  } finally {
    clearTimeout(timer);
  }
}

const SearchSchema = Type.Object({
  q: Type.String({ minLength: 1 }),
  top_k: Type.Optional(Type.Number({ minimum: 1, maximum: 50 })),
  source: Type.Optional(Type.Union([Type.Literal("local"), Type.Literal("feishu")])),
  tag: Type.Optional(Type.String()),
  from: Type.Optional(Type.String()),
  to: Type.Optional(Type.String()),
});

const DocSchema = Type.Object({
  doc_id: Type.String({ minLength: 1 }),
});

const SyncNowSchema = Type.Object({
  scope: Type.Union([Type.Literal("local"), Type.Literal("feishu"), Type.Literal("all"), Type.Literal("market"), Type.Literal("financials")]),
  mode: Type.Union([Type.Literal("full"), Type.Literal("incremental")]),
  reason: Type.Union([Type.Literal("manual"), Type.Literal("schedule"), Type.Literal("miss")]),
});

const MarketQuoteSchema = Type.Object({
  symbol: Type.String({ minLength: 1 }),
  asset_class: Type.Union([Type.Literal("stock"), Type.Literal("crypto")]),
});

const MarketHistorySchema = Type.Object({
  symbol: Type.String({ minLength: 1 }),
  asset_class: Type.Union([Type.Literal("stock"), Type.Literal("crypto")]),
  days: Type.Optional(Type.Number({ minimum: 1, maximum: 3650 })),
});

const FinancialsSchema = Type.Object({
  entity_id: Type.String({ minLength: 1 }),
  entity_type: Type.Union([Type.Literal("stock"), Type.Literal("protocol")]),
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 200 })),
});

const OnchainProtocolSchema = Type.Object({
  protocol: Type.String({ minLength: 1 }),
  days: Type.Optional(Type.Number({ minimum: 1, maximum: 3650 })),
});

const OnchainChainSchema = Type.Object({
  chain: Type.String({ minLength: 1 }),
  days: Type.Optional(Type.Number({ minimum: 1, maximum: 3650 })),
});

const OnchainLiquiditySchema = Type.Object({
  token: Type.String({ minLength: 1 }),
  chain: Type.String({ minLength: 1 }),
  days: Type.Optional(Type.Number({ minimum: 1, maximum: 3650 })),
});

const WebSearchSchema = Type.Object({
  q: Type.String({ minLength: 1 }),
  count: Type.Optional(Type.Number({ minimum: 1, maximum: 20 })),
  freshness: Type.Optional(Type.Union([Type.Literal("pd"), Type.Literal("pw"), Type.Literal("pm"), Type.Literal("py")])),
  country: Type.Optional(Type.String({ minLength: 2, maxLength: 2 })),
  search_lang: Type.Optional(Type.String()),
});

const WebReadSchema = Type.Object({
  url: Type.String({ minLength: 1 }),
  max_chars: Type.Optional(Type.Number({ minimum: 1000, maximum: 30000 })),
});

const BitableCreateSchema = Type.Object({
  name: Type.String({ minLength: 1 }),
  fields: Type.Array(Type.Object({
    name: Type.String({ minLength: 1 }),
    type: Type.String({ minLength: 1 }),
  })),
  records: Type.Array(Type.Any()),
  folder_token: Type.Optional(Type.String()),
});

const MacroIndicatorSchema = Type.Object({
  series_id: Type.String({ minLength: 1 }),
  days: Type.Optional(Type.Number({ minimum: 1, maximum: 7300 })),
});

const SymbolSchema = Type.Object({
  symbol: Type.String({ minLength: 1 }),
});

const SymbolLimitSchema = Type.Object({
  symbol: Type.String({ minLength: 1 }),
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 100 })),
});

const ForexPairSchema = Type.Object({
  pair: Type.String({ minLength: 3 }),
});

const ForexHistorySchema = Type.Object({
  pair: Type.String({ minLength: 3 }),
  days: Type.Optional(Type.Number({ minimum: 1, maximum: 3650 })),
});

const OptionsChainSchema = Type.Object({
  symbol: Type.String({ minLength: 1 }),
  expiry: Type.Optional(Type.String()),
});

const KolWatchlistAddSchema = Type.Object({
  name: Type.String({ minLength: 1 }),
  title: Type.Optional(Type.String()),
  category: Type.Optional(Type.String()),
  owner_id: Type.Optional(Type.String({ description: "Auto-injected by hook — do not fill manually" })),
});

const KolWatchlistRemoveSchema = Type.Object({
  name: Type.String({ minLength: 1 }),
  owner_id: Type.Optional(Type.String({ description: "Auto-injected by hook — do not fill manually" })),
});

const KolWatchlistListSchema = Type.Object({
  category: Type.Optional(Type.String()),
  owner_id: Type.Optional(Type.String({ description: "Auto-injected by hook — do not fill manually" })),
});

const EmptySchema = Type.Object({});

const StructuredReportsSchema = Type.Object({
  company: Type.Optional(Type.String()),
  sector: Type.Optional(Type.String()),
  report_type: Type.Optional(Type.String()),
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 100 })),
});

const ThesesSchema = Type.Object({
  company: Type.Optional(Type.String()),
  direction: Type.Optional(Type.Union([
    Type.Literal("bullish"), Type.Literal("bearish"), Type.Literal("neutral"),
  ])),
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 100 })),
});

const MetricsSchema = Type.Object({
  company: Type.Optional(Type.String()),
  ticker: Type.Optional(Type.String()),
  metric: Type.Optional(Type.String()),
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 200 })),
});

// ── Tool call statistics (in-memory, resets on gateway restart) ──
const toolStats = {};

function getToolStat(name) {
  if (!toolStats[name]) {
    toolStats[name] = { calls: 0, errors: 0, totalMs: 0 };
  }
  return toolStats[name];
}

// ── Parameter auto-correction rules ──
const SYMBOL_PARAMS = new Set(["symbol", "token"]);
const PAIR_PARAMS = new Set(["pair"]);
const LOWERCASE_PARAMS = new Set(["protocol", "chain"]);

function correctParams(toolName, params) {
  const corrected = { ...params };
  let changed = false;
  for (const [key, val] of Object.entries(corrected)) {
    if (typeof val !== "string") continue;
    if (SYMBOL_PARAMS.has(key)) {
      const upper = val.toUpperCase();
      if (upper !== val) { corrected[key] = upper; changed = true; }
    } else if (PAIR_PARAMS.has(key)) {
      const fixed = val.replace(/[\s/\-]/g, "").toUpperCase();
      if (fixed !== val) { corrected[key] = fixed; changed = true; }
    } else if (LOWERCASE_PARAMS.has(key)) {
      const lower = val.toLowerCase();
      if (lower !== val) { corrected[key] = lower; changed = true; }
    }
  }
  return changed ? corrected : null;
}

// ── Large result truncation for context saving ──
const TRUNCATE_TOOLS = new Set([
  "market_get_history", "forex_history", "options_chain",
]);
const KEEP_ITEMS = 3;

function truncateArrayInObj(obj) {
  if (Array.isArray(obj) && obj.length > KEEP_ITEMS * 2) {
    const total = obj.length;
    return [
      ...obj.slice(0, KEEP_ITEMS),
      { _truncated: true, _summary: `... ${total - KEEP_ITEMS * 2} items omitted (${total} total) ...` },
      ...obj.slice(-KEEP_ITEMS),
    ];
  }
  if (obj && typeof obj === "object" && !Array.isArray(obj)) {
    let changed = false;
    const result = {};
    for (const [k, v] of Object.entries(obj)) {
      const tv = truncateArrayInObj(v);
      if (tv !== v) changed = true;
      result[k] = tv;
    }
    return changed ? result : obj;
  }
  return obj;
}

// ── Per-session sender tracking (for owner_id injection) ──
let _lastSender = null;

const plugin = {
  id: "openclaw-report-db",
  name: "Report DB",
  description: "Beiduoduo local report query tools",
  configSchema: emptyPluginConfigSchema(),
  register(api) {
    // ── Hook: message_received — capture sender open_id ──
    api.on("message_received", (event) => {
      if (event.from) {
        _lastSender = event.from;
      }
    });

    // ── Hook: after_tool_call — statistics ──
    api.on("after_tool_call", (event) => {
      const stat = getToolStat(event.toolName);
      stat.calls++;
      if (event.error) stat.errors++;
      if (event.durationMs) stat.totalMs += event.durationMs;
    });

    // ── Hook: before_tool_call — param auto-correction + guardrails + owner_id injection ──
    api.on("before_tool_call", (event) => {
      // Guardrail: block full sync without explicit confirmation flow
      if (event.toolName === "report_sync_now") {
        const p = event.params;
        if (p.scope === "all" || p.mode === "full") {
          return {
            block: true,
            blockReason: "全量同步(scope=all 或 mode=full)是高开销操作。请先向用户确认是否真的需要全量同步，建议使用 scope=feishu, mode=incremental 替代。",
          };
        }
      }

      // Auto-inject owner_id for KOL watchlist tools
      if (event.toolName.startsWith("kol_watchlist_") && _lastSender) {
        const corrected = correctParams(event.toolName, event.params);
        return { params: { ...(corrected || event.params), owner_id: _lastSender } };
      }

      const corrected = correctParams(event.toolName, event.params);
      if (corrected) {
        return { params: corrected };
      }
    });

    // ── Hook: tool_result_persist — truncate large results (SYNC) ──
    api.on("tool_result_persist", (event) => {
      if (!event.toolName || !TRUNCATE_TOOLS.has(event.toolName)) return;
      const msg = event.message;
      if (!msg || !msg.content) return;
      let modified = false;
      const newContent = msg.content.map((block) => {
        if (block.type !== "text" || !block.text) return block;
        try {
          const parsed = JSON.parse(block.text);
          const truncated = truncateArrayInObj(parsed);
          if (truncated !== parsed) {
            modified = true;
            return { ...block, text: JSON.stringify(truncated, null, 2) };
          }
        } catch { /* not JSON, leave as-is */ }
        return block;
      });
      if (modified) {
        return { message: { ...msg, content: newContent } };
      }
    });

    // ── HTTP Route: /api/tool-stats ──
    api.registerHttpRoute({
      path: "/api/tool-stats",
      handler(_req, res) {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ stats: toolStats, timestamp: new Date().toISOString() }, null, 2));
      },
    });
    api.registerTool(
      {
        name: "report_search",
        label: "Report Search",
        description: "Search indexed research documents in local+feishu mirror. USE WHEN: free-text search for report paragraphs/content. NOT FOR: browsing reports by company/sector (use report_structured_list).",
        parameters: SearchSchema,
        async execute(_toolCallId, params) {
          const p = params;
          const query = new URLSearchParams();
          query.set("q", p.q);
          if (p.top_k) query.set("top_k", String(p.top_k));
          if (p.source) query.set("source", p.source);
          if (p.tag) query.set("tag", p.tag);
          if (p.from) query.set("from", p.from);
          if (p.to) query.set("to", p.to);
          return json(await request(api, `/v1/search?${query.toString()}`));
        },
      },
      { name: "report_search" },
    );

    api.registerTool(
      {
        name: "report_get_doc",
        label: "Report Get Doc",
        description: "Fetch a normalized document payload by doc_id.",
        parameters: DocSchema,
        async execute(_toolCallId, params) {
          return json(await request(api, `/v1/docs/${encodeURIComponent(params.doc_id)}`));
        },
      },
      { name: "report_get_doc" },
    );

    api.registerTool(
      {
        name: "report_sync_now",
        label: "Report Sync Now",
        description: "Trigger sync job for local/feishu/all sources.",
        parameters: SyncNowSchema,
        async execute(_toolCallId, params) {
          return json(
            await request(api, "/v1/sync/run", {
              method: "POST",
              body: JSON.stringify(params),
            }),
          );
        },
      },
      { name: "report_sync_now" },
    );

    api.registerTool(
      {
        name: "report_sync_status",
        label: "Report Sync Status",
        description: "Check sync status and recent runs.",
        parameters: EmptySchema,
        async execute() {
          return json(await request(api, "/v1/sync/status"));
        },
      },
      { name: "report_sync_status" },
    );

    // ── Web Search ──

    api.registerTool(
      {
        name: "web_search",
        label: "Web Search",
        description: "Search the web via DuckDuckGo. Use for finding relevant pages. Supports freshness filter: pd=24h, pw=7days, pm=30days, py=1year. To read full page content, use web_read with the URL.",
        parameters: WebSearchSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("q", params.q);
          if (params.count) query.set("count", String(params.count));
          if (params.freshness) query.set("freshness", params.freshness);
          if (params.country) query.set("country", params.country);
          if (params.search_lang) query.set("search_lang", params.search_lang);
          return json(await request(api, `/v1/web/search?${query.toString()}`));
        },
      },
      { name: "web_search" },
    );

    api.registerTool(
      {
        name: "web_read",
        label: "Web Read",
        description: "Fetch a web page and extract its full text content using Playwright. Use after web_search to read the actual page content. Pass the URL from search results.",
        parameters: WebReadSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("url", params.url);
          if (params.max_chars) query.set("max_chars", String(params.max_chars));
          return json(await request(api, `/v1/web/read?${query.toString()}`));
        },
      },
      { name: "web_read" },
    );

    // ── Market & On-chain Tools ──

    api.registerTool(
      {
        name: "market_get_quote",
        label: "Market Quote",
        description: "Get latest price quote for a stock or crypto asset.",
        parameters: MarketQuoteSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("symbol", params.symbol);
          query.set("asset_class", params.asset_class);
          return json(await request(api, `/v1/market/quote?${query.toString()}`));
        },
      },
      { name: "market_get_quote" },
    );

    api.registerTool(
      {
        name: "market_get_history",
        label: "Market History",
        description: "Get historical OHLCV data for a stock or crypto. Only use when the user explicitly asks for data analysis — for price trend viewing, send a TradingView link instead (see TOOLS.md).",
        parameters: MarketHistorySchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("symbol", params.symbol);
          query.set("asset_class", params.asset_class);
          if (params.days) query.set("days", String(params.days));
          query.set("chart", "false");
          return json(await request(api, `/v1/market/history?${query.toString()}`));
        },
      },
      { name: "market_get_history" },
    );

    api.registerTool(
      {
        name: "financials_get",
        label: "Financials",
        description: "Get financial statements for a stock (SEC EDGAR) or crypto protocol (Artemis).",
        parameters: FinancialsSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("entity_id", params.entity_id);
          query.set("entity_type", params.entity_type);
          if (params.limit) query.set("limit", String(params.limit));
          return json(await request(api, `/v1/financials?${query.toString()}`));
        },
      },
      { name: "financials_get" },
    );

    api.registerTool(
      {
        name: "onchain_protocol",
        label: "Onchain Protocol",
        description: "Get on-chain protocol metrics (TVL, revenue, fees, active users).",
        parameters: OnchainProtocolSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("protocol", params.protocol);
          if (params.days) query.set("days", String(params.days));
          return json(await request(api, `/v1/onchain/protocol?${query.toString()}`));
        },
      },
      { name: "onchain_protocol" },
    );

    api.registerTool(
      {
        name: "onchain_chain",
        label: "Onchain Chain",
        description: "Get on-chain metrics for a blockchain (gas, TPS, active addresses, TVL).",
        parameters: OnchainChainSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("chain", params.chain);
          if (params.days) query.set("days", String(params.days));
          return json(await request(api, `/v1/onchain/chain?${query.toString()}`));
        },
      },
      { name: "onchain_chain" },
    );

    api.registerTool(
      {
        name: "onchain_liquidity",
        label: "Onchain Liquidity",
        description: "Get DEX liquidity metrics for a token on a specific chain.",
        parameters: OnchainLiquiditySchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("token", params.token);
          query.set("chain", params.chain);
          if (params.days) query.set("days", String(params.days));
          return json(await request(api, `/v1/onchain/liquidity?${query.toString()}`));
        },
      },
      { name: "onchain_liquidity" },
    );

    // ── Macro & Enhanced Data (OpenBB) ──

    api.registerTool(
      {
        name: "macro_indicator",
        label: "Macro Indicator",
        description: "Query a US macro economic indicator from FRED. series_id can be: GDP, CPI, FEDFUNDS (联邦基金利率), UNRATE (失业率), DGS10 (10年国债), M2SL (M2货币供应), or any raw FRED series ID.",
        parameters: MacroIndicatorSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("series_id", params.series_id);
          if (params.days) query.set("days", String(params.days));
          return json(await request(api, `/v1/macro/indicator?${query.toString()}`));
        },
      },
      { name: "macro_indicator" },
    );

    api.registerTool(
      {
        name: "macro_overview",
        label: "Macro Overview",
        description: "Get a snapshot of key US macro indicators: GDP, CPI, Fed Funds Rate, Unemployment, 10Y Treasury, M2. One call gives the full picture.",
        parameters: EmptySchema,
        async execute() {
          return json(await request(api, "/v1/macro/overview"));
        },
      },
      { name: "macro_overview" },
    );

    api.registerTool(
      {
        name: "equity_profile",
        label: "Equity Profile",
        description: "Company overview: sector, industry, market cap, P/E, P/B, dividend yield, 52-week range, beta. Use for '苹果是什么行业' or 'AAPL market cap'.",
        parameters: SymbolSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("symbol", params.symbol);
          return json(await request(api, `/v1/equity/profile?${query.toString()}`));
        },
      },
      { name: "equity_profile" },
    );

    api.registerTool(
      {
        name: "equity_ratios",
        label: "Equity Ratios",
        description: "Financial valuation ratios: P/E, P/B, P/S, EV/EBITDA, ROE, ROA, profit margin, debt-to-equity. Use for '特斯拉PE多少' or 'compare AAPL vs MSFT valuations'.",
        parameters: SymbolSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("symbol", params.symbol);
          return json(await request(api, `/v1/equity/ratios?${query.toString()}`));
        },
      },
      { name: "equity_ratios" },
    );

    api.registerTool(
      {
        name: "equity_analysts",
        label: "Analyst Estimates",
        description: "Analyst consensus: target price (high/low/mean), recommendation (buy/hold/sell), EPS & revenue estimates. Use for '分析师怎么看AAPL' or 'NVDA target price'.",
        parameters: SymbolSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("symbol", params.symbol);
          return json(await request(api, `/v1/equity/analysts?${query.toString()}`));
        },
      },
      { name: "equity_analysts" },
    );

    api.registerTool(
      {
        name: "equity_insiders",
        label: "Insider Trading",
        description: "Recent insider (executive/director) buy/sell activity. Use for '特斯拉最近有内部人买入吗' or 'AAPL insider transactions'.",
        parameters: SymbolLimitSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("symbol", params.symbol);
          if (params.limit) query.set("limit", String(params.limit));
          return json(await request(api, `/v1/equity/insiders?${query.toString()}`));
        },
      },
      { name: "equity_insiders" },
    );

    api.registerTool(
      {
        name: "equity_institutions",
        label: "Institutional Holders",
        description: "Top institutional shareholders (Vanguard, BlackRock, etc.) and their holdings. Use for '谁是AAPL最大股东' or 'institutional ownership of TSLA'.",
        parameters: SymbolSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("symbol", params.symbol);
          return json(await request(api, `/v1/equity/institutions?${query.toString()}`));
        },
      },
      { name: "equity_institutions" },
    );

    api.registerTool(
      {
        name: "forex_quote",
        label: "Forex Quote",
        description: "Real-time foreign exchange rate. pair format: USDCNY, EURUSD, USDJPY, GBPUSD. Use for '今天人民币汇率' or 'EUR to USD rate'.",
        parameters: ForexPairSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("pair", params.pair);
          return json(await request(api, `/v1/forex/quote?${query.toString()}`));
        },
      },
      { name: "forex_quote" },
    );

    api.registerTool(
      {
        name: "forex_history",
        label: "Forex History",
        description: "Historical forex rates (OHLC). Use for '人民币过去一年走势' or 'EURUSD trend last 90 days'.",
        parameters: ForexHistorySchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("pair", params.pair);
          if (params.days) query.set("days", String(params.days));
          return json(await request(api, `/v1/forex/history?${query.toString()}`));
        },
      },
      { name: "forex_history" },
    );

    api.registerTool(
      {
        name: "options_chain",
        label: "Options Chain",
        description: "Options chain data: strikes, calls, puts, IV, Greeks, open interest, volume. Use for 'AAPL下周五到期的期权' or 'TSLA options IV'.",
        parameters: OptionsChainSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          query.set("symbol", params.symbol);
          if (params.expiry) query.set("expiry", params.expiry);
          return json(await request(api, `/v1/options/chain?${query.toString()}`));
        },
      },
      { name: "options_chain" },
    );

    // ── Bitable ──

    api.registerTool(
      {
        name: "bitable_create",
        label: "Bitable Create",
        description: "Create a Feishu Bitable (multi-dimensional spreadsheet) with structured data. Use after fetching data with financials_get or other data tools.",
        parameters: BitableCreateSchema,
        async execute(_toolCallId, params) {
          const body = {
            name: params.name,
            fields: params.fields,
            records: params.records,
          };
          if (params.folder_token) body.folder_token = params.folder_token;
          return json(
            await request(api, "/v1/bitable/create", {
              method: "POST",
              body: JSON.stringify(body),
            }),
          );
        },
      },
      { name: "bitable_create" },
    );

    // ── KOL Watchlist Tools ──

    api.registerTool(
      {
        name: "kol_watchlist_add",
        label: "KOL Watchlist Add",
        description: "Add a person to the KOL observation list. Use when user says '帮我关注 Sam Altman' or 'add Elon Musk to watchlist'. Provide name (required), title (e.g. 'OpenAI CEO'), and category (crypto/tech/ai/macro).",
        parameters: KolWatchlistAddSchema,
        async execute(_toolCallId, params) {
          const body = { name: params.name };
          if (params.title) body.title = params.title;
          if (params.category) body.category = params.category;
          if (params.owner_id) body.owner_id = params.owner_id;
          return json(
            await request(api, "/v1/kol/watchlist", {
              method: "POST",
              body: JSON.stringify(body),
            }),
          );
        },
      },
      { name: "kol_watchlist_add" },
    );

    api.registerTool(
      {
        name: "kol_watchlist_remove",
        label: "KOL Watchlist Remove",
        description: "Remove a person from the KOL observation list (soft delete). Use when user says '不要关注 Vitalik 了' or '把 XX 从名单里删了'.",
        parameters: KolWatchlistRemoveSchema,
        async execute(_toolCallId, params) {
          const body = { name: params.name };
          if (params.owner_id) body.owner_id = params.owner_id;
          return json(
            await request(api, "/v1/kol/watchlist/disable", {
              method: "POST",
              body: JSON.stringify(body),
            }),
          );
        },
      },
      { name: "kol_watchlist_remove" },
    );

    api.registerTool(
      {
        name: "kol_watchlist_list",
        label: "KOL Watchlist List",
        description: "List all people in your KOL observation list. Use when user says '看看我的观察名单' or '我在关注谁'. Optional category filter (crypto/tech/ai/macro). Each user sees only their own list.",
        parameters: KolWatchlistListSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          if (params.category) query.set("category", params.category);
          if (params.owner_id) query.set("owner_id", params.owner_id);
          return json(await request(api, `/v1/kol/watchlist?${query.toString()}`));
        },
      },
      { name: "kol_watchlist_list" },
    );

    // ── Structured Report Tools ──

    api.registerTool(
      {
        name: "report_structured_list",
        label: "Structured Reports",
        description: "Search structured research reports by company, sector, or report type. Returns enriched metadata including summaries, quality scores, and classifications. USE WHEN: browsing/filtering reports by company, sector, or type. NOT FOR: searching text content (use report_search).",
        parameters: StructuredReportsSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          if (params.company) query.set("company", params.company);
          if (params.sector) query.set("sector", params.sector);
          if (params.report_type) query.set("report_type", params.report_type);
          if (params.limit) query.set("limit", String(params.limit));
          return json(await request(api, `/v1/reports/structured?${query.toString()}`));
        },
      },
      { name: "report_structured_list" },
    );

    api.registerTool(
      {
        name: "report_structured_get",
        label: "Structured Report Detail",
        description: "Get a single report's full structured data: metadata, investment theses, and financial metrics.",
        parameters: DocSchema,
        async execute(_toolCallId, params) {
          return json(await request(api, `/v1/reports/${encodeURIComponent(params.doc_id)}/structured`));
        },
      },
      { name: "report_structured_get" },
    );

    api.registerTool(
      {
        name: "report_theses",
        label: "Investment Theses",
        description: "Search investment theses across all reports. Filter by company or direction (bullish/bearish/neutral). USE WHEN: asking about bullish/bearish views, investment opinions, catalysts, risks. NOT FOR: looking up financial numbers (use report_metrics). Examples: '哪些研报看多ETH', 'bearish views on Coinbase'.",
        parameters: ThesesSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          if (params.company) query.set("company", params.company);
          if (params.direction) query.set("direction", params.direction);
          if (params.limit) query.set("limit", String(params.limit));
          return json(await request(api, `/v1/theses?${query.toString()}`));
        },
      },
      { name: "report_theses" },
    );

    api.registerTool(
      {
        name: "report_metrics",
        label: "Financial Metrics",
        description: "Search financial metrics extracted from reports. Filter by company, ticker, or metric name. USE WHEN: looking up specific financial numbers (revenue, TVL, users, etc.) from research reports. NOT FOR: investment opinions (use report_theses). Examples: 'Coinbase收入', 'ETH TVL data'.",
        parameters: MetricsSchema,
        async execute(_toolCallId, params) {
          const query = new URLSearchParams();
          if (params.company) query.set("company", params.company);
          if (params.ticker) query.set("ticker", params.ticker);
          if (params.metric) query.set("metric", params.metric);
          if (params.limit) query.set("limit", String(params.limit));
          return json(await request(api, `/v1/metrics?${query.toString()}`));
        },
      },
      { name: "report_metrics" },
    );

    api.registerTool(
      {
        name: "report_structurize_stats",
        label: "Structurize Stats",
        description: "Check the progress of report structurization: how many reports have been processed for metadata, theses, and metrics extraction.",
        parameters: EmptySchema,
        async execute() {
          return json(await request(api, "/v1/reports/stats"));
        },
      },
      { name: "report_structurize_stats" },
    );
  },
};

export default plugin;
