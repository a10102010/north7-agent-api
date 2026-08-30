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
}


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

    return _text({"error": f"Unknown tool: {name}"})


from mcp_types._types import PaginatedRequestParams as _PRP
server.add_request_handler("tools/list", _PRP, handle_list_tools)
server.add_request_handler("tools/call", types.CallToolRequestParams, handle_call_tool)

# ── Streamable HTTP app ──
# host="0.0.0.0" disables auto DNS rebinding protection (we're behind nginx)
_inner_app = server.streamable_http_app(host="0.0.0.0")


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

        if not api_key:
            error_resp = self._jsonrpc_error(
                rpc_id, -32001,
                "Authentication required. Provide API key via 'Authorization: Bearer n7_live_...' or 'X-API-Key' header. "
                "Get your key at https://north7.ai/api"
            )
            response = Response(
                content=json.dumps(error_resp),
                status_code=401,
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
            status = 429 if 'rate limit' in error_msg.lower() else 403
            response = Response(
                content=json.dumps(error_resp),
                status_code=status,
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
