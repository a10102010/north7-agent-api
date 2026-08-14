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
            "Get real-time trading signals from 6 AI-powered sources: "
            "news analysis (5min), alpha screening (daily), stock radar, "
            "intraday scanner (30min), commodity scoring, index/forex picks."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Filter: news_5m, alpha_14d, radar_daily, intraday_30m, scr_daily. Omit for all.",
                    "enum": ["news_5m", "alpha_14d", "radar_daily", "intraday_30m", "scr_daily"],
                }
            },
        },
    ),
    types.Tool(
        name="get_risk_index",
        description="Global market risk index (0-100). Includes crises, regional scores. Higher = more risk.",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="get_market_regime",
        description="Detect market regime: BULL, BEAR, SIDEWAYS, or CRISIS. Based on SPX vs 200d MA and VIX.",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="get_prices",
        description="Real-time prices for 80+ assets (stocks, ETFs, commodities, forex). Updated every 2 min.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "string",
                    "description": "Comma-separated symbols e.g. 'AAPL,MSFT,TSLA'. Omit for all.",
                }
            },
        },
    ),
    types.Tool(
        name="get_stock_analysis",
        description="Deep AI analysis for a stock: fundamentals, technicals, AI assessment.",
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Ticker symbol e.g. AAPL, MSFT, TSLA"}
            },
            "required": ["ticker"],
        },
    ),
    types.Tool(
        name="get_intelligence_briefing",
        description="AI-generated daily intelligence briefing. Geopolitics, market-moving events, analysis.",
        inputSchema={
            "type": "object",
            "properties": {
                "lang": {"type": "string", "description": "en or de", "enum": ["en", "de"], "default": "en"}
            },
        },
    ),
    types.Tool(
        name="get_commodity_signals",
        description="Commodity scoring for 15 raw materials (gold, oil, wheat, coffee etc.) with seasonal patterns.",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="get_sector_radar",
        description="Sector rotation radar: breadth and momentum across market sectors.",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="get_model_portfolio",
        description="Current model portfolio positions and performance.",
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
