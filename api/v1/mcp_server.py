"""NORTH7 MCP Server — Model Context Protocol for AI Agents.

Exposes NORTH7 market intelligence as MCP tools that any
Claude, GPT, or MCP-compatible agent can discover and use.

Auth: API key required for tools/call (same key/credit system as REST API).
Discovery (initialize, tools/list) is open so agents can explore tools.

Run: python3 -m api.v1.mcp_server
Endpoint: https://north7.ai/mcp/ (Streamable HTTP)
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from mcp.server import Server
from mcp import types
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import Response

from api.v1.auth import validate_request, ENDPOINT_COSTS

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')

# ── MCP tool name -> auth endpoint mapping (for credit costs) ──
TOOL_ENDPOINT_MAP = {
    'get_trading_signals':      'signals_latest',
    'get_risk_index':           'risk',
    'get_market_regime':        'regime',
    'get_prices':               'prices',
    'get_stock_analysis':       'analysis',
    'get_intelligence_briefing':'intelligence',
    'get_commodity_signals':    'commodities',
    'get_sector_radar':         'sector_radar',
    'get_model_portfolio':      'portfolio',
    'get_events':               'events',
    'get_agent_context':        'agent_context',
    'get_impact':               'impact',
    'get_relationships':        'relationships',
}

# Tools that work without API key (same as REST free endpoints)
FREE_TOOLS = {'get_risk_index', 'get_market_regime', 'get_events', 'get_agent_context', 'get_impact', 'get_relationships'}


def _load_json(filename: str, default=None):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


# ── Create MCP Server ──
server = Server("north7-market-intelligence")

# ── Tool definitions ──
TOOLS = [
    types.Tool(
        name="get_trading_signals",
        description=(
            "Retrieve AI-generated trading signals from 6 independent sources. "
            "Use this tool when you need actionable trade ideas with direction (LONG/SHORT), "
            "confidence scores (0-100), and AI-generated reasoning. "
            "Sources: news_5m (breaking news analysis, updated every 5 min), "
            "alpha_14d (daily highest-conviction stock picks), "
            "radar_daily (technical stock radar), "
            "intraday_30m (momentum scanner, updated every 30 min during market hours), "
            "scr_daily (commodity signals for 15 raw materials). "
            "Returns a list of signal objects each containing: symbol, type, direction, confidence, and reason. "
            "Call get_risk_index and get_market_regime first to assess conditions before acting on signals. "
            "Costs 1 credit per call. FREE endpoints (risk, regime) require no API key."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Filter signals by source type. Options: news_5m (breaking news, 5-min updates), alpha_14d (daily conviction picks), radar_daily (technical radar), intraday_30m (momentum scanner), scr_daily (commodity signals). Omit to receive signals from all sources combined.",
                    "enum": ["news_5m", "alpha_14d", "radar_daily", "intraday_30m", "scr_daily"],
                }
            },
        },
    ),
    types.Tool(
        name="get_risk_index",
        description=(
            "Get the global market risk index scored 0-100. "
            "Use this tool FIRST before any trading decision to assess whether market conditions are favorable. "
            "Score interpretation: 0-30 = CALM (low risk, favorable for trading), "
            "30-50 = MODERATE (normal conditions), "
            "50-70 = ELEVATED (increased caution advised), "
            "70-100 = CRITICAL (crisis-level, defensive positioning recommended). "
            "Returns: value (0-100), status (CALM/MODERATE/ELEVATED/CRITICAL), "
            "active crises list, and per-region risk scores (Middle East, Europe, Asia, Americas). "
            "Data sources: GDELT geopolitical events, VIX, credit spreads, macro indicators. "
            "Updated every 30 minutes. FREE — no API key required."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="get_market_regime",
        description=(
            "Detect the current market regime to inform trading strategy. "
            "Use this tool alongside get_risk_index before making trading decisions. "
            "Returns one of four regimes: BULL (S&P 500 above 200-day MA, VIX below 20), "
            "BEAR (S&P 500 below 200-day MA), "
            "SIDEWAYS (range-bound, low directional conviction), "
            "CRISIS (extreme volatility, VIX above 30). "
            "Also returns: confidence percentage, S&P 500 price vs 200-day MA, "
            "current VIX level, and regime duration. "
            "Updated every 30 minutes. FREE — no API key required."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="get_prices",
        description=(
            "Fetch real-time price data for 80+ assets across stocks, ETFs, commodities, and forex. "
            "Use this tool when you need current market prices, daily price changes, or percentage moves. "
            "Returns for each asset: symbol, price, change (absolute), changePercent, volume, and timestamp. "
            "Prices are sourced from Yahoo Finance and updated every 2 minutes during market hours. "
            "You can request specific symbols or omit the parameter to receive all 80+ assets. "
            "Costs 1 credit per call."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "string",
                    "description": "Comma-separated ticker symbols to filter results, e.g. 'AAPL,MSFT,TSLA,GC=F,EURUSD=X'. Use standard Yahoo Finance ticker format. Omit this parameter to receive prices for all 80+ tracked assets.",
                }
            },
        },
    ),
    types.Tool(
        name="get_stock_analysis",
        description=(
            "Get a comprehensive AI-generated analysis for a specific stock. "
            "Use this tool when you need detailed information about a company before making an investment decision. "
            "Returns: fundamental data (P/E, revenue, margins, market cap), "
            "technical indicators (RSI, moving averages, support/resistance), "
            "AI assessment with bull/bear case, rating (BUY/HOLD/SELL), "
            "and a confidence score. "
            "Analysis is generated using Claude AI and covers both quantitative metrics and qualitative factors. "
            "Costs 5 credits per call. The ticker parameter is required."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol in uppercase, e.g. 'AAPL' for Apple, 'MSFT' for Microsoft, 'TSLA' for Tesla, 'NVDA' for NVIDIA. Use standard US ticker format."
                }
            },
            "required": ["ticker"],
        },
    ),
    types.Tool(
        name="get_intelligence_briefing",
        description=(
            "Retrieve the daily AI-generated geopolitical intelligence briefing. "
            "Use this tool to understand macro-level events that could impact markets: "
            "geopolitical developments, central bank decisions, trade policy changes, "
            "sanctions, military conflicts, and economic data releases. "
            "Returns: headline events with market impact scores (1-10), "
            "affected sectors and assets, risk assessment, and actionable implications. "
            "The briefing is generated daily using Claude AI analyzing 40+ global news sources. "
            "Available in English and German. Costs 10 credits per call."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "lang": {
                    "type": "string",
                    "description": "Language for the briefing. 'en' for English (default), 'de' for German (Deutsch).",
                    "enum": ["en", "de"],
                    "default": "en"
                }
            },
        },
    ),
    types.Tool(
        name="get_commodity_signals",
        description=(
            "Get AI-scored trading signals for 15 raw material commodities. "
            "Use this tool for commodity-specific intelligence including: "
            "gold, silver, crude oil, natural gas, wheat, corn, soybeans, coffee, cocoa, sugar, "
            "cotton, copper, platinum, palladium, and lumber. "
            "Returns for each commodity: current score (0-100), direction (LONG/SHORT), "
            "seasonal pattern analysis, supply chain risk factors, and AI reasoning. "
            "Particularly useful for supply chain risk assessment and commodity trading decisions. "
            "Costs 2 credits per call."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="get_sector_radar",
        description=(
            "Analyze sector rotation and market breadth across major market sectors. "
            "Use this tool to identify which sectors are gaining or losing momentum, "
            "helping with sector allocation and rotation strategies. "
            "Returns: top-performing and worst-performing sectors, "
            "breadth indicators (advance/decline ratio), momentum scores, "
            "and sector-level technical analysis. "
            "Covers: Technology, Healthcare, Financials, Energy, Consumer, Industrials, "
            "Materials, Utilities, Real Estate, and Communication Services. "
            "Costs 2 credits per call."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="get_model_portfolio",
        description=(
            "View the current NORTH7 model portfolio positions and performance metrics. "
            "Use this tool to see what positions the NORTH7 system is currently holding, "
            "including entry prices, current P&L, position sizes, and overall portfolio performance. "
            "Returns: list of active positions (symbol, direction, entry price, current price, P&L percentage), "
            "total portfolio return, and performance history. "
            "The model portfolio is a transparent, logged research portfolio — not investment advice. "
            "Costs 10 credits per call."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="get_events",
        description=(
            "Get structured geopolitical and market events with impact scores. "
            "Each event includes: headline, impact_score (1-10), affected sectors, "
            "affected assets, region, and confidence. Use this to detect market-moving "
            "events and filter by minimum impact or region. "
            "Returns events sorted by impact score, highest first. "
            "FREE — no API key needed. "
            "Example: get_events with min_impact=7 returns only high-impact events."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "min_impact": {
                    "type": "number",
                    "description": "Minimum impact score (1-10). Default 0 returns all events. Use 7+ for high-impact only.",
                },
                "region": {
                    "type": "string",
                    "description": "Filter by region: 'Middle East', 'Europe', 'North America', 'South Asia', 'East Asia', 'Eastern Europe', 'Africa'",
                },
            },
        },
    ),
    types.Tool(
        name="get_agent_context",
        description=(
            "Get full market awareness in a single call — the recommended FIRST tool "
            "for any trading agent. Returns: risk index (0-100) with trend, "
            "market regime (BULL/BEAR/SIDEWAYS/CRISIS) with VIX, "
            "agent guidance (DEFENSIVE/CAUTIOUS/FAVORABLE), "
            "active crises, hot regions with scores, signal summary, "
            "and recommended next API calls. "
            "This combines /risk + /regime + /events into one response. "
            "FREE — no API key needed."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="get_impact",
        description=(
            "Map geopolitical events and crises to specific asset impacts. "
            "Returns which assets are positively or negatively affected by current events, "
            "with directional bias (BUY/SELL), confidence score, driver explanation, "
            "and timeframe (short_term/medium_term). "
            "Filter by specific asset to see all factors affecting it. "
            "Combines crisis analysis, news signals, alpha screening, and commodity scoring. "
            "FREE — no API key needed."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "asset": {
                    "type": "string",
                    "description": "Filter by asset ticker, e.g. 'AAPL', 'CL=F' (crude oil), 'GC=F' (gold), 'NVDA'. Omit for all impacts.",
                },
            },
        },
    ),
    types.Tool(
        name="get_relationships",
        description=(
            "Query the NORTH7 knowledge graph of entities and relationships. "
            "Entities: countries, companies, assets, commodities, sectors, crises, regions. "
            "Shows how entities are connected — e.g. which assets Iran affects, "
            "what commodities a crisis impacts, which sectors are linked to a country. "
            "Use entity parameter to query a specific entity (e.g. 'IR' for Iran, "
            "'CL=F' for oil, 'energy' for energy sector). "
            "Returns matched entities, connected nodes, and weighted edges with evidence. "
            "FREE — no API key needed."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Entity ID to query: country code (IR, US, CN), ticker (AAPL, CL=F), sector (energy, defense), or name.",
                },
                "type": {
                    "type": "string",
                    "description": "Filter by entity type: country, company, asset, commodity, sector, crisis, region",
                },
            },
        },
    ),
]


# ── Register handlers via add_request_handler ──

async def handle_list_tools(ctx, params):
    return types.ListToolsResult(tools=TOOLS)


async def handle_call_tool(ctx, params):
    name = params.name
    arguments = params.arguments or {}

    def _text(data):
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(data, indent=2, ensure_ascii=False))])

    if name == "get_trading_signals":
        source = arguments.get("source")
        signals = []
        if not source or source == "news_5m":
            news = _load_json("signals.json", [])
            if isinstance(news, list):
                signals.extend([{"symbol": s.get("symbol", s.get("ticker", "")), "type": "news_5m", "direction": s.get("direction", s.get("signal", "")), "confidence": s.get("confidence"), "reason": s.get("reason_en", s.get("reason", ""))} for s in news])
        if not source or source == "alpha_14d":
            alpha = _load_json("alpha_signals.json", {})
            signals.extend([{"symbol": s.get("symbol", ""), "type": "alpha_14d", "direction": s.get("direction", "long"), "confidence": s.get("confidence", s.get("score")), "reason": s.get("reason_en", s.get("reason", ""))} for s in alpha.get("signals", [])])
        if not source or source == "radar_daily":
            radar = _load_json("stock_radar.json", {})
            signals.extend([{"symbol": s.get("symbol", ""), "type": "radar_daily", "direction": s.get("direction", "long"), "confidence": s.get("confidence", s.get("score")), "reason": s.get("reason_en", s.get("reason", ""))} for s in radar.get("recommendations", [])])
        if not source or source == "intraday_30m":
            intra = _load_json("intraday_scanner.json", {})
            signals.extend([{"symbol": s.get("symbol", ""), "type": "intraday_30m", "direction": s.get("direction", s.get("signal", "")), "confidence": s.get("confidence"), "reason": s.get("reason_en", s.get("reason", ""))} for s in intra.get("signals", [])])
        if not source or source == "scr_daily":
            scr = _load_json("scr.json", {})
            if isinstance(scr, dict) and scr.get("signals"):
                signals.extend([{"symbol": s.get("symbol", ""), "type": "scr_daily", "direction": s.get("direction", ""), "confidence": s.get("confidence", s.get("score")), "reason": s.get("reason_en", s.get("reason", ""))} for s in scr["signals"]])
        return _text({"signals": signals, "count": len(signals)})

    elif name == "get_risk_index":
        return _text(_load_json("risk.json", {}))

    elif name == "get_market_regime":
        return _text(_load_json("regime.json", {}))

    elif name == "get_prices":
        prices = _load_json("prices.json", [])
        # prices.json is a list of {symbol, price, change, ...}
        if isinstance(prices, list):
            symbols = arguments.get("symbols")
            if symbols:
                requested = [s.strip().upper() for s in symbols.split(",")]
                prices = [p for p in prices if p.get("symbol", "").upper() in requested]
            return _text({"prices": prices, "count": len(prices)})
        # Fallback for dict format
        symbols = arguments.get("symbols")
        if symbols:
            requested = [s.strip().upper() for s in symbols.split(",")]
            prices = {k: v for k, v in prices.items() if k.upper() in requested}
        return _text(prices)

    elif name == "get_stock_analysis":
        ticker = arguments.get("ticker", "")
        analyses = _load_json("stock_analyses.json", {})
        result = analyses.get(ticker.upper()) or analyses.get(ticker.lower()) or analyses.get(ticker)
        if not result:
            fund = _load_json("fundamentals_cache.json", {})
            result = fund.get(ticker.upper()) or fund.get(ticker.lower())
        return _text(result or {"error": f"No analysis for {ticker}"})

    elif name == "get_intelligence_briefing":
        lang = arguments.get("lang", "en")
        daily = _load_json("daily_de.json" if lang == "de" else "daily_en.json", _load_json("daily.json", {}))
        return _text(daily)

    elif name == "get_commodity_signals":
        return _text({"scr": _load_json("scr.json", {}), "translations": _load_json("scr_en.json", {})})

    elif name == "get_sector_radar":
        return _text(_load_json("sector_radar.json", {}))

    elif name == "get_model_portfolio":
        return _text({"portfolio": _load_json("portfolio.json", {}), "performance": _load_json("performance.json", {})})

    elif name == "get_events":
        risk_data = _load_json("risk.json", {})
        daily = _load_json("daily_en.json", {})
        min_impact = float(arguments.get("min_impact", 0))
        region_filter = arguments.get("region", "")
        events = []
        for i, crisis in enumerate(risk_data.get("crises", [])):
            cl = crisis.lower()
            region = "Global"
            if any(w in cl for w in ["iran", "hormuz", "middle east"]): region = "Middle East"
            elif any(w in cl for w in ["ukraine", "russia"]): region = "Eastern Europe"
            elif any(w in cl for w in ["china", "taiwan", "japan"]): region = "East Asia"
            elif any(w in cl for w in ["india", "nepal", "pakistan"]): region = "South Asia"
            elif any(w in cl for w in ["us ", "canada", "fed ", "treasury", "tariff"]): region = "North America"
            elif any(w in cl for w in ["europe", "ecb"]): region = "Europe"
            elif any(w in cl for w in ["africa", "sudan", "ebola"]): region = "Africa"
            impact = 8.5 if any(w in cl for w in ["crisis", "collapse", "war"]) else 7.0 if any(w in cl for w in ["escalat", "surge"]) else 6.0
            if impact >= min_impact and (not region_filter or region_filter.lower() in region.lower()):
                events.append({"id": f"evt_{i+1}", "headline": crisis, "impact_score": impact, "region": region})
        for sig in daily.get("signals_detail", []):
            events.append({"id": f"evt_sig_{len(events)}", "type": sig.get("type",""), "asset": sig.get("asset",""), "rationale": sig.get("rationale",""), "sources": sig.get("sources",[])})
        return _text({"events": events, "count": len(events), "risk_level": risk_data.get("value", 0)})

    elif name == "get_agent_context":
        risk_data = _load_json("risk.json", {})
        regime_data = _load_json("regime.json", {})
        rv = risk_data.get("value", 50)
        rg = regime_data.get("regime", "UNKNOWN")
        if rv >= 80: guidance = "DEFENSIVE"
        elif rv >= 60: guidance = "CAUTIOUS"
        elif rg == "BULL" and rv < 40: guidance = "FAVORABLE"
        elif rg == "BEAR": guidance = "BEARISH"
        else: guidance = "NEUTRAL"
        hot = [{"name": r["name"], "score": r["score"]} for r in risk_data.get("regions", []) if r.get("score", 0) >= 60]
        return _text({"risk": {"value": rv, "status": risk_data.get("status",""), "trend": "rising" if rv>=70 else "stable"}, "regime": {"current": rg, "spx": regime_data.get("spx_value"), "vix": regime_data.get("vix_value")}, "guidance": guidance, "crises": risk_data.get("crises",[])[:5], "hot_regions": hot})

    elif name == "get_impact":
        risk_data = _load_json("risk.json", {})
        signals = _load_json("signals.json", [])
        alpha = _load_json("alpha_signals.json", {})
        asset_filter = arguments.get("asset", "")
        impacts = []
        if isinstance(signals, list):
            for s in signals:
                sym = s.get("asset", s.get("symbol", ""))
                if asset_filter and asset_filter.upper() not in sym.upper(): continue
                if sym: impacts.append({"asset": sym, "direction": s.get("direction",""), "confidence": s.get("confidence"), "driver": s.get("reason_en", s.get("reason",""))[:200], "source": "news"})
        for s in alpha.get("signals", []):
            sym = s.get("symbol", "")
            if asset_filter and asset_filter.upper() not in sym.upper(): continue
            if sym: impacts.append({"asset": sym, "direction": s.get("direction","long"), "confidence": s.get("confidence", s.get("score")), "driver": s.get("reason_en", s.get("reason",""))[:200], "source": "alpha"})
        return _text({"impacts": impacts, "count": len(impacts), "risk": risk_data.get("value", 0), "regime": _load_json("regime.json", {}).get("regime","")})

    elif name == "get_relationships":
        graph = _load_json("event_graph.json", {})
        nodes = graph.get("nodes", {})
        edges = graph.get("edges", [])
        entity = arguments.get("entity", "")
        etype = arguments.get("type", "")
        if entity:
            el = entity.lower()
            matched = [k for k, n in nodes.items() if el == n.get("id","").lower() or el in n.get("name","").lower() or el in k.lower()]
            conn_edges = [e for e in edges if e["from"] in matched or e["to"] in matched]
            conn_keys = set(matched)
            for e in conn_edges: conn_keys.add(e["from"]); conn_keys.add(e["to"])
            return _text({"entity": entity, "found": bool(matched), "nodes": [nodes[k] for k in conn_keys if k in nodes], "edges": conn_edges})
        elif etype:
            filtered = [v for v in nodes.values() if v.get("type") == etype]
            return _text({"type": etype, "nodes": filtered, "count": len(filtered)})
        else:
            return _text({"node_count": graph.get("node_count",0), "edge_count": graph.get("edge_count",0), "entity_types": graph.get("entity_types",{})})

    return _text({"error": f"Unknown tool: {name}"})


from mcp_types._types import PaginatedRequestParams as _PRP
server.add_request_handler("tools/list", _PRP, handle_list_tools)
server.add_request_handler("tools/call", types.CallToolRequestParams, handle_call_tool)

# ── Streamable HTTP app ──
# host="0.0.0.0" disables auto DNS rebinding protection (we're behind nginx)
_inner_app = server.streamable_http_app(host="0.0.0.0")


# ── Health check for Glama/mcp-proxy ──
from starlette.routing import Route

async def ping(request):
    return Response(content='{status:ok}', status_code=200, media_type='application/json')

# ── Auth Middleware ──
class MCPAuthMiddleware:
    """ASGI middleware that enforces API key auth on MCP tools/call requests.

    - initialize, tools/list: open (no key needed) so agents can discover tools
    - tools/call: requires valid API key via Authorization or X-API-Key header
    - Credits are deducted using the same cost table as the REST API
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Health check for Glama/mcp-proxy
        request = Request(scope, receive)
        if request.method == "GET" and request.url.path.rstrip('/') in ('/ping', '/mcp/ping'):
            response = Response(
                content='{"status":"ok"}',
                status_code=200,
                media_type='application/json',
            )
            await response(scope, receive, send)
            return

        # We need to inspect POST body to check if it's a tools/call request.
        # Read the body, check the JSON-RPC method, then replay it to the inner app.
        request = Request(scope, receive)

        # Only POST requests carry JSON-RPC payloads
        if request.method != "POST":
            await self.app(scope, receive, send)
            return

        # Read body bytes
        body = await request.body()

        # Try to parse JSON-RPC method
        rpc_method = None
        rpc_id = None
        tool_name = None
        try:
            payload = json.loads(body)
            rpc_method = payload.get("method", "")
            rpc_id = payload.get("id")
            if rpc_method == "tools/call":
                params = payload.get("params", {})
                tool_name = params.get("name", "")
        except (json.JSONDecodeError, AttributeError):
            pass

        # Only enforce auth on tools/call
        if rpc_method != "tools/call":
            # Replay body to inner app
            await self._forward(scope, body, send)
            return

        # Extract API key from headers
        api_key = None
        headers = dict(scope.get("headers", []))
        # Headers are bytes tuples
        for key, val in scope.get("headers", []):
            header_name = key.decode("latin-1").lower()
            header_val = val.decode("latin-1")
            if header_name == "authorization":
                # Bearer token
                if header_val.lower().startswith("bearer "):
                    api_key = header_val[7:].strip()
                else:
                    api_key = header_val.strip()
            elif header_name == "x-api-key":
                api_key = header_val.strip()

        # Free tools don't need auth
        if tool_name in FREE_TOOLS:
            await self._forward(scope, body, send)
            return

        if not api_key:
            error_resp = self._jsonrpc_error(
                rpc_id, -32001,
                "Authentication required. Provide API key via 'Authorization: Bearer n7_live_...' or 'X-API-Key' header. "
                "Get your free key at https://north7.ai/api"
            )
            response = Response(
                content=json.dumps(error_resp),
                status_code=200,
                media_type="application/json",
            )
            await response(scope, receive, send)
            return

        # Map tool name to endpoint for credit cost
        endpoint = TOOL_ENDPOINT_MAP.get(tool_name, 'signals_latest')

        # Validate key and deduct credits
        ok, error_msg, key_data = validate_request(api_key, endpoint)
        if not ok:
            error_resp = self._jsonrpc_error(rpc_id, -32001, error_msg)
            response = Response(
                content=json.dumps(error_resp),
                status_code=200,
                media_type="application/json",
            )
            await response(scope, receive, send)
            return

        # Auth passed — forward to MCP server
        await self._forward(scope, body, send)

    async def _forward(self, scope: Scope, body: bytes, send: Send):
        """Forward request with pre-read body to the inner ASGI app."""
        import asyncio
        body_sent = False
        disconnect_event = asyncio.Event()

        async def replay_receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            # After body is sent, wait indefinitely for disconnect
            # (SSE/streaming connections stay open)
            await disconnect_event.wait()
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    @staticmethod
    def _jsonrpc_error(req_id, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message,
            },
        }


# Wrap the MCP app with auth middleware
mcp_app = MCPAuthMiddleware(_inner_app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(mcp_app, host="127.0.0.1", port=8791)
