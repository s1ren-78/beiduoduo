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

const EmptySchema = Type.Object({});

const plugin = {
  id: "openclaw-report-db",
  name: "Report DB",
  description: "Beiduoduo local report query tools",
  configSchema: emptyPluginConfigSchema(),
  register(api) {
    api.registerTool(
      {
        name: "report_search",
        label: "Report Search",
        description: "Search indexed research documents in local+feishu mirror.",
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
  },
};

export default plugin;
