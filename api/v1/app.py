"""NORTH7 Agent API v1 — Financial Intelligence for AI Agents.

The world's first agent-native financial intelligence API.
Built for autonomous AI trading agents, not just humans.

Features:
- 3 FREE endpoints (no API key needed) — try before you sign up
- 12 authenticated endpoints with credits
- Rate limit headers on every response
- Rich error messages with hints for agents
- OpenAPI 3.1 with agent-optimized descriptions
- MCP, A2A, and .well-known discovery

Run: uvicorn api.v1.app:app --host 127.0.0.1 --port 8790
"""
from __future__ import annotations

import hmac
import json
import os
import sys
import time
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from api.v1.auth import (
    ENDPOINT_COSTS,
    TIERS,
    validate_request,
    create_api_key,
    get_key_info,
    add_credits,
    list_all_keys,
)
from api.v1.schemas import N7Response, N7Error

# ── Config ──
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
ADMIN_TOKEN = os.environ.get('N7_ADMIN_TOKEN', '')
ACCESS_LOG_PATH = os.path.join(DATA_DIR, 'api_access_log.json')
ACCESS_LOG_MAX = 10_000

AGENT_INSTRUCTIONS = (
    "NORTH7 provides AI-analyzed financial intelligence, NOT raw market data. "
    "Use /v1/risk and /v1/regime FIRST to assess market conditions before requesting signals. "
    "The risk index (0-100) tells you whether to be cautious; the regime (BULL/BEAR/SIDEWAYS/CRISIS) "
    "tells you the current market phase. Then use /v1/signals/latest for actionable trade signals. "
    "All signal endpoints return a 'confidence' score (0-1) and a 'reason' in English. "
    "Rate limits are returned in response headers (X-RateLimit-Remaining). "
    "FREE endpoints (/v1/risk, /v1/regime, /v1/health) require NO API key — use them anytime. "
    "For authenticated endpoints, pass your key via the X-API-Key header. "
    "Credits are deducted per call (most cost 1-2 credits). Check /v1/account for balance."
)

# ── IP Rate Limiting (in-memory) ──
FREE_ENDPOINTS = {'/v1/risk', '/v1/regime', '/v1/health'}
FREE_RATE_LIMIT = 10  # requests per minute
_ip_requests: dict[str, list[float]] = defaultdict(list)


def _get_client_ip(request: Request) -> str:
    """Extract client IP from proxy headers or direct connection."""
    ip = request.headers.get('X-Real-IP')
    if ip:
        return ip
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'


def _check_free_rate_limit(ip: str) -> bool:
    """Return True if IP is within rate limit, False if exceeded."""
    now = time.time()
    window_start = now - 60
    # Clean old entries
    _ip_requests[ip] = [t for t in _ip_requests[ip] if t > window_start]
    if len(_ip_requests[ip]) >= FREE_RATE_LIMIT:
        return False
    _ip_requests[ip].append(now)
    return True


# ── Access Logging (async, non-blocking) ──
_log_lock = asyncio.Lock()


async def _log_access(ip: str, endpoint: str, api_key_prefix: str, user_agent: str):
    """Log API access asynchronously without blocking the response."""
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'ip': ip,
        'endpoint': endpoint,
        'api_key_prefix': api_key_prefix,
        'user_agent': user_agent[:200] if user_agent else '',
    }
    try:
        async with _log_lock:
            # Read existing log
            if os.path.exists(ACCESS_LOG_PATH):
                with open(ACCESS_LOG_PATH) as f:
                    log = json.load(f)
            else:
                log = []
            log.append(entry)
            # Trim to max entries (keep newest)
            if len(log) > ACCESS_LOG_MAX:
                log = log[-ACCESS_LOG_MAX:]
            with open(ACCESS_LOG_PATH, 'w') as f:
                json.dump(log, f)
    except Exception:
        pass  # Never let logging break the API


# ── Security Headers Middleware ──
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        return response


# ── Access Logging Middleware ──
class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Extract info before response
        ip = _get_client_ip(request)
        endpoint = request.url.path
        api_key = request.headers.get('X-API-Key', '')
        api_key_prefix = api_key[:8] + '...' if len(api_key) > 12 else api_key if api_key else 'none'
        user_agent = request.headers.get('User-Agent', '')

        response = await call_next(request)

        # Fire-and-forget logging (non-blocking)
        asyncio.create_task(_log_access(ip, endpoint, api_key_prefix, user_agent))

        return response


# ── App ──
app = FastAPI(
    title="NORTH7 Agent API",
    version="1.0.0",
    summary="Real-time AI-analyzed trading signals, risk assessment, and market intelligence for autonomous agents.",
    description=(
        "## Financial Intelligence Infrastructure for AI Agents\n\n"
        "NORTH7 provides **decision-ready market intelligence** — not raw data. "
        "Every signal comes with AI-generated confidence scores, reasoning, and context.\n\n"
        "### Free Endpoints (no API key needed)\n"
        "- `GET /v1/risk` — Global risk index 0-100 with active crises\n"
        "- `GET /v1/regime` — Market regime: BULL / BEAR / SIDEWAYS / CRISIS\n"
        "- `GET /v1/health` — API status and data freshness\n\n"
        "### Agent Integration\n"
        "- **MCP Server**: `https://north7.ai/mcp` (9 tools)\n"
        "- **A2A Agent Card**: `https://north7.ai/.well-known/agent.json`\n"
        "- **AI Plugin**: `https://north7.ai/.well-known/ai-plugin.json`\n\n"
        "### How to Use\n"
        f"{AGENT_INSTRUCTIONS}\n\n"
        "### Pricing\n"
        "| Tier | Credits | Rate Limit | Price |\n"
        "|------|---------|------------|-------|\n"
        "| Free | 1,000 | 10/min | Free |\n"
        "| Starter | 50,000 | 60/min | 5 EUR |\n"
        "| Pro | 500,000 | 300/min | 25 EUR |\n"
        "| Enterprise | Unlimited | 1,000/min | Custom |\n"
    ),
    docs_url="/v1/docs",
    redoc_url="/v1/redoc",
    openapi_url="/v1/openapi.json",
    contact={"name": "NORTH7 Support", "email": "support@north7.ai", "url": "https://north7.ai/developers"},
    license_info={"name": "Proprietary", "url": "https://north7.ai/disclaimer"},
    openapi_tags=[
        {"name": "Free", "description": "No API key required. Use these endpoints to evaluate NORTH7 before signing up. Safe to call anytime."},
        {"name": "Signals", "description": "AI-analyzed trading signals from 6 sources. Each signal includes symbol, direction, confidence score, and reasoning."},
        {"name": "Market", "description": "Real-time market data: prices, price history. Updated every 2 minutes from Yahoo Finance."},
        {"name": "Analysis", "description": "Deep AI analysis for individual stocks and sectors. Includes fundamentals, technicals, and AI assessment."},
        {"name": "Intelligence", "description": "AI-generated briefings covering geopolitics, market-moving events, and forward-looking analysis."},
        {"name": "Portfolio", "description": "NORTH7 model portfolio positions and performance tracking."},
        {"name": "Account", "description": "API key management, credit balance, and usage statistics."},
        {"name": "Admin", "description": "Key creation and credit management. Requires X-Admin-Token header."},
    ],
)

# Middleware order matters: last added = first executed
# So we add SecurityHeaders first, then AccessLog, then CORS
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://north7.ai", "https://www.north7.ai", "https://north7.at"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-Credits-Used", "X-Credits-Remaining"],
)


# ── Helpers ──

def _load_json(filename: str, default=None):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def _auth(api_key: str, endpoint: str) -> dict:
    """Validate API key and return key_data or raise with agent-friendly errors."""
    if not api_key:
        raise HTTPException(401, detail={
            "error": "Missing API key",
            "hint": "Pass your API key via the X-API-Key header. Example: curl -H 'X-API-Key: n7_live_...' https://north7.ai/v1/signals/latest",
            "free_endpoints": ["/v1/risk", "/v1/regime", "/v1/health"],
            "get_key": "Get a free key instantly at https://north7.ai/developers (1,000 credits, no payment)",
        })
    ok, err, key_data = validate_request(api_key, endpoint)
    if not ok:
        if 'Insufficient credits' in err:
            raise HTTPException(402, detail={
                "error": err,
                "hint": "Your credits are exhausted. Contact support@north7.ai to add more credits.",
                "current_credits": key_data.get('credits', 0) if key_data else 0,
                "endpoint_cost": ENDPOINT_COSTS.get(endpoint, 1),
            })
        if 'Rate limit' in err:
            raise HTTPException(429, detail={
                "error": err,
                "hint": f"You exceeded your rate limit. Wait 60 seconds or upgrade your tier for higher limits.",
                "retry_after_seconds": 60,
                "current_tier": key_data.get('tier', 'unknown') if key_data else 'unknown',
            })
        raise HTTPException(401, detail={
            "error": err,
            "hint": "Check that your API key is correct and starts with 'n7_live_'.",
        })
    return key_data


def _meta(endpoint: str, key_data: dict, sources: list[str] = None) -> dict:
    return {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'endpoint': endpoint,
        'credits_used': ENDPOINT_COSTS.get(endpoint, 1),
        'credits_remaining': key_data.get('credits', 0),
        'sources': sources or [],
        'version': '1.0.0',
        'next': _suggest_next(endpoint),
    }


def _suggest_next(endpoint: str) -> dict:
    """Suggest the next logical endpoint — guides agents through a workflow."""
    suggestions = {
        'risk': {'endpoint': '/v1/regime', 'reason': 'Check market regime to contextualize the risk level'},
        'regime': {'endpoint': '/v1/signals/latest', 'reason': 'Get trading signals aligned with the current regime'},
        'signals_latest': {'endpoint': '/v1/analysis/{ticker}', 'reason': 'Deep-dive into a specific signal with full analysis'},
        'signals_alpha': {'endpoint': '/v1/prices?symbols=...', 'reason': 'Check current prices for the alpha signals'},
        'prices': {'endpoint': '/v1/signals/latest', 'reason': 'Get AI signals for the assets you are tracking'},
        'analysis': {'endpoint': '/v1/portfolio/model', 'reason': 'See how the NORTH7 model portfolio positions this asset'},
        'portfolio': {'endpoint': '/v1/intelligence/briefing', 'reason': 'Get the daily briefing for macro context'},
        'intelligence': {'endpoint': '/v1/risk', 'reason': 'Check the real-time risk index for current conditions'},
        'sector_radar': {'endpoint': '/v1/signals/latest?source=radar_daily', 'reason': 'Get signals from the stock radar'},
        'commodities': {'endpoint': '/v1/signals/latest?source=scr_daily', 'reason': 'Get commodity trading signals'},
        'intraday': {'endpoint': '/v1/risk', 'reason': 'Check risk before acting on intraday signals'},
    }
    return suggestions.get(endpoint, {'endpoint': '/v1/', 'reason': 'See all available endpoints'})


def _respond(data, endpoint: str, key_data: dict, sources: list[str] = None):
    resp = N7Response(ok=True, data=data, meta=_meta(endpoint, key_data, sources))
    return JSONResponse(
        content=resp.model_dump(),
        headers={
            'X-RateLimit-Limit': str(key_data.get('rate_limit', 60)),
            'X-RateLimit-Remaining': str(max(0, key_data.get('rate_limit', 60) - 1)),
            'X-Credits-Used': str(ENDPOINT_COSTS.get(endpoint, 1)),
            'X-Credits-Remaining': str(key_data.get('credits', 0)),
        },
    )


def _admin_check(token: str):
    """Accept both static N7_ADMIN_TOKEN and session-based admin tokens from sessions.json."""
    if not token:
        raise HTTPException(401, detail="Missing X-Admin-Token header")
    # 1) Static env token
    if ADMIN_TOKEN and hmac.compare_digest(token, ADMIN_TOKEN):
        return
    # 2) Session token from sessions.json (admin login in admin.html)
    try:
        sessions_path = os.path.join(DATA_DIR, "sessions.json")
        if os.path.exists(sessions_path):
            with open(sessions_path) as f:
                sessions = json.load(f)
            sess = sessions.get(token)
            if sess and sess.get("role") == "admin":
                exp = sess.get("expires_at", "")
                if exp:
                    from datetime import datetime as _dt
                    exp_dt = _dt.fromisoformat(exp.replace("Z", "+00:00"))
                    now = _dt.now(timezone.utc) if exp_dt.tzinfo else _dt.now()
                    if exp_dt > now:
                        return
    except Exception:
        pass
    raise HTTPException(401, detail="Invalid admin token")


def _free_meta(endpoint: str, sources: list[str] = None) -> dict:
    return {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'endpoint': endpoint,
        'credits_used': 0,
        'auth_required': False,
        'sources': sources or [],
        'version': '1.0.0',
        'upgrade': 'Get a free API key for 1,000 credits at support@north7.ai',
        'next': _suggest_next(endpoint),
    }


# ══════════════════════════════════════════════════
# FREE ENDPOINTS (no API key needed!)
# These are the hook — agents discover and try these,
# then upgrade for signals, analysis, portfolio.
# ══════════════════════════════════════════════════

@app.get("/v1/risk", tags=["Free"],
    summary="Global Market Risk Index",
    description=(
        "Returns the global market risk index (0-100) with active crises and regional breakdown. "
        "**NO API KEY REQUIRED** — call this anytime to assess market conditions.\n\n"
        "USE THIS ENDPOINT to determine whether market conditions are favorable for trading. "
        "Risk > 70 means elevated risk, consider reducing exposure. "
        "Risk > 85 means crisis-level risk, defensive positioning recommended.\n\n"
        "The response includes:\n"
        "- `value`: Risk score 0-100\n"
        "- `status`: CALM / MODERATE / ELEVATED / CRITICAL\n"
        "- `crises`: List of active global crises affecting markets\n"
        "- `regions`: Per-region risk scores (Middle East, Europe, Asia etc.)\n\n"
        "Data sources: GDELT geopolitical event database, Yahoo Finance volatility data, "
        "USGS seismic data, weather/climate feeds. Updated every 30 minutes."
    ),
    response_description="Risk index with crises and regional breakdown",
    operation_id="getRiskIndex",
    responses={200: {"description": "Risk data returned successfully"}},
)
async def risk_index(request: Request, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    # If key provided, use credits. Otherwise, free with rate limit.
    if x_api_key:
        kd = _auth(x_api_key, 'risk')
        risk = _load_json('risk.json', {})
        return _respond(risk, 'risk', kd, ['gdelt', 'yahoo_finance', 'weather_data', 'usgs_seismic'])
    # Free tier: check IP rate limit
    ip = _get_client_ip(request)
    if not _check_free_rate_limit(ip):
        raise HTTPException(429, detail={
            "error": "Rate limit exceeded for free tier. Get an API key for higher limits.",
            "hint": "Contact support@north7.ai for a free API key (1,000 credits, 60 req/min).",
            "retry_after_seconds": 60,
        })
    risk = _load_json('risk.json', {})
    return {'ok': True, 'data': risk, 'meta': _free_meta('risk', ['gdelt', 'yahoo_finance', 'weather_data'])}


@app.get("/v1/regime", tags=["Free"],
    summary="Market Regime Detection",
    description=(
        "Detects the current market regime: **BULL**, **BEAR**, **SIDEWAYS**, or **CRISIS**. "
        "**NO API KEY REQUIRED** — call this anytime.\n\n"
        "USE THIS ENDPOINT to determine the market phase before making trading decisions. "
        "Based on S&P 500 position relative to its 200-day moving average and VIX volatility level.\n\n"
        "Interpretation:\n"
        "- **BULL**: SPX above 200d MA, VIX calm — favor long positions\n"
        "- **BEAR**: SPX below 200d MA — favor short/defensive positions\n"
        "- **SIDEWAYS**: Mixed signals — reduce position sizes\n"
        "- **CRISIS**: VIX spike + rapid decline — cash/hedging recommended\n\n"
        "The response includes SPX value, 200d MA, VIX level, and reasoning."
    ),
    response_description="Current market regime with reasoning",
    operation_id="getMarketRegime",
)
async def market_regime(request: Request, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    if x_api_key:
        kd = _auth(x_api_key, 'regime')
        regime = _load_json('regime.json', {})
        return _respond(regime, 'regime', kd, ['sp500_history', 'vix', 'risk_model'])
    # Free tier: check IP rate limit
    ip = _get_client_ip(request)
    if not _check_free_rate_limit(ip):
        raise HTTPException(429, detail={
            "error": "Rate limit exceeded for free tier. Get an API key for higher limits.",
            "hint": "Contact support@north7.ai for a free API key (1,000 credits, 60 req/min).",
            "retry_after_seconds": 60,
        })
    regime = _load_json('regime.json', {})
    return {'ok': True, 'data': regime, 'meta': _free_meta('regime', ['sp500_history', 'vix'])}


@app.get("/v1/health", tags=["Free"],
    summary="API Health Check",
    description=(
        "Returns API health status and data freshness. **NO API KEY REQUIRED.**\n\n"
        "Use this to verify that the API is operational and data is current before "
        "making trading decisions based on NORTH7 signals."
    ),
    operation_id="getHealthStatus",
)
async def health(request: Request, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    # Rate limit only if no API key
    if not x_api_key:
        ip = _get_client_ip(request)
        if not _check_free_rate_limit(ip):
            raise HTTPException(429, detail={
                "error": "Rate limit exceeded for free tier. Get an API key for higher limits.",
                "hint": "Contact support@north7.ai for a free API key (1,000 credits, 60 req/min).",
                "retry_after_seconds": 60,
            })
    prices = _load_json('prices.json', {})
    risk = _load_json('risk.json', {})
    signals = _load_json('signals.json', [])
    alpha = _load_json('alpha_signals.json', {})
    regime = _load_json('regime.json', {})
    return {
        'status': 'ok',
        'version': '1.0.0',
        'uptime_info': 'API runs 24/7 with automatic failover',
        'data_freshness': {
            'prices': {'count': len(prices) if isinstance(prices, dict) else 0, 'update_interval': '2 minutes'},
            'risk': {'updated': risk.get('updated', 'unknown'), 'update_interval': '30 minutes'},
            'signals': {'count': len(signals) if isinstance(signals, list) else 0, 'update_interval': '10 minutes'},
            'alpha': {'date': alpha.get('date', 'unknown'), 'update_interval': 'daily 07:00 UTC'},
            'regime': {'value': regime.get('regime', 'unknown'), 'as_of': regime.get('as_of', 'unknown')},
        },
        'free_endpoints': ['/v1/risk', '/v1/regime', '/v1/health'],
        'mcp_server': 'https://north7.ai/mcp',
        'docs': 'https://north7.ai/v1/docs',
        'agent_card': 'https://north7.ai/.well-known/agent.json',
    }


# ══════════════════════════════════════════════════
# AUTHENTICATED ENDPOINTS (API Key required)
# ══════════════════════════════════════════════════

@app.get("/v1/signals/latest", tags=["Signals"],
    summary="Get All Trading Signals",
    description=(
        "Returns real-time trading signals from all 6 AI-powered sources. "
        "Each signal includes symbol, direction, confidence score (0-1), and AI-generated reasoning.\n\n"
        "**Signal Sources:**\n"
        "- `news_5m` — Breaking news analysis (every 10 min, Claude AI)\n"
        "- `alpha_14d` — Mid-term alpha screening (daily, fundamental + technical)\n"
        "- `radar_daily` — Stock radar picks (daily, momentum + quality)\n"
        "- `intraday_30m` — Intraday momentum scanner (every 30 min Mon-Fri)\n"
        "- `scr_daily` — Commodity scoring for 15 raw materials (daily)\n\n"
        "**How to use:** Call /v1/regime first to know the market phase. "
        "In a BULL regime, focus on long signals with confidence > 0.7. "
        "In BEAR, focus on short signals or defensive sectors.\n\n"
        "Filter by source with the `source` parameter to get only specific signal types."
    ),
    operation_id="getTradingSignals",
)
async def signals_latest(
    x_api_key: str = Header(None, alias="X-API-Key"),
    source: Optional[str] = Query(None, description="Filter by source: news_5m, alpha_14d, radar_daily, intraday_30m, scr_daily. Omit to get all sources."),
):
    kd = _auth(x_api_key, 'signals_latest')
    signals = []
    sources_used = []

    if not source or source in ('news_5m', 'news'):
        news = _load_json('signals.json', [])
        if isinstance(news, list):
            for s in news:
                signals.append({
                    'symbol': s.get('symbol', s.get('ticker', '')),
                    'signal_type': 'news_5m',
                    'direction': s.get('direction', s.get('signal', '')),
                    'confidence': s.get('confidence'),
                    'reason_en': s.get('reason_en', s.get('reason', '')),
                    'reason_de': s.get('reason_de', ''),
                    'source': 'news_5m',
                    'generated_utc': s.get('timestamp', s.get('generated_utc', '')),
                })
            sources_used.append('news_5m')

    if not source or source in ('alpha_14d', 'alpha'):
        alpha = _load_json('alpha_signals.json', {})
        for s in alpha.get('signals', []):
            signals.append({
                'symbol': s.get('symbol', s.get('ticker', '')),
                'signal_type': 'alpha_14d',
                'direction': s.get('direction', 'long'),
                'confidence': s.get('confidence', s.get('score')),
                'risk_score': s.get('risk_score'),
                'reason_en': s.get('reason_en', s.get('reason', '')),
                'reason_de': s.get('reason_de', ''),
                'source': 'alpha_14d',
                'generated_utc': alpha.get('generated_utc', ''),
            })
        sources_used.append('alpha_14d')

    if not source or source in ('radar_daily', 'radar'):
        radar = _load_json('stock_radar.json', {})
        for s in radar.get('recommendations', []):
            signals.append({
                'symbol': s.get('symbol', s.get('ticker', '')),
                'signal_type': 'radar_daily',
                'direction': s.get('direction', 'long'),
                'confidence': s.get('confidence', s.get('score')),
                'reason_en': s.get('reason_en', s.get('reason', '')),
                'reason_de': s.get('reason_de', ''),
                'source': 'radar_daily',
                'generated_utc': radar.get('updated', ''),
            })
        sources_used.append('radar_daily')

    if not source or source in ('intraday_30m', 'intraday'):
        intra = _load_json('intraday_scanner.json', {})
        for s in intra.get('signals', []):
            signals.append({
                'symbol': s.get('symbol', s.get('ticker', '')),
                'signal_type': 'intraday_30m',
                'direction': s.get('direction', s.get('signal', '')),
                'confidence': s.get('confidence'),
                'reason_en': s.get('reason_en', s.get('reason', '')),
                'reason_de': s.get('reason_de', ''),
                'source': 'intraday_30m',
                'generated_utc': intra.get('updated', ''),
            })
        sources_used.append('intraday_30m')

    if not source or source in ('scr_daily', 'scr', 'commodities'):
        scr = _load_json('scr.json', {})
        if isinstance(scr, dict) and (scr.get('signals') or scr.get('commodities')):
            for s in (scr.get('signals') or scr.get('commodities', [])):
                signals.append({
                    'symbol': s.get('symbol', ''),
                    'signal_type': 'scr_daily',
                    'direction': s.get('direction', ''),
                    'confidence': s.get('confidence', s.get('score')),
                    'reason_en': s.get('reason_en', s.get('reason', '')),
                    'reason_de': s.get('reason_de', ''),
                    'source': 'scr_daily',
                    'generated_utc': scr.get('updated', ''),
                })
            sources_used.append('scr_daily')

    return _respond({'signals': signals, 'count': len(signals)}, 'signals_latest', kd, sources_used)


@app.get("/v1/signals/alpha", tags=["Signals"],
    summary="Alpha Daily Signals",
    description=(
        "AI-screened mid-term opportunities with 14-day outlook. "
        "These are the highest-conviction signals from fundamental + technical analysis.\n\n"
        "Updated daily at 07:00 UTC. Each signal includes a quality score and detailed reasoning."
    ),
    operation_id="getAlphaSignals",
)
async def signals_alpha(x_api_key: str = Header(None, alias="X-API-Key")):
    kd = _auth(x_api_key, 'signals_alpha')
    alpha = _load_json('alpha_signals.json', {})
    return _respond(alpha, 'signals_alpha', kd, ['alpha_daily', 'yahoo_finance', 'claude_analysis'])


@app.get("/v1/prices", tags=["Market"],
    summary="Real-Time Asset Prices",
    description=(
        "Real-time prices for 80+ tracked assets including stocks, ETFs, commodities, and forex. "
        "Updated every 2 minutes from Yahoo Finance.\n\n"
        "Use the `symbols` parameter to request specific assets (comma-separated). "
        "Omit to get all tracked assets.\n\n"
        "Example: `/v1/prices?symbols=AAPL,MSFT,TSLA,GC=F,EURUSD=X`"
    ),
    operation_id="getAssetPrices",
)
async def prices(
    x_api_key: str = Header(None, alias="X-API-Key"),
    symbols: Optional[str] = Query(None, description="Comma-separated ticker symbols. Example: AAPL,MSFT,TSLA. Omit for all 80+ assets."),
):
    kd = _auth(x_api_key, 'prices')
    all_prices = _load_json('prices.json', {})
    # Handle both list and dict format
    if isinstance(all_prices, list):
        if symbols:
            requested = [s.strip().upper() for s in symbols.split(',')]
            filtered = [p for p in all_prices if p.get('symbol', '').upper() in requested]
            if not filtered:
                raise HTTPException(404, detail={
                    "error": f"No prices found for: {symbols}",
                    "hint": "Check symbol format. Use Yahoo Finance tickers: AAPL, MSFT, GC=F (gold), EURUSD=X (forex).",
                    "available_count": len(all_prices),
                })
            return _respond({"prices": filtered, "count": len(filtered)}, 'prices', kd, ['yahoo_finance'])
        return _respond({"prices": all_prices, "count": len(all_prices)}, 'prices', kd, ['yahoo_finance'])
    # Dict format fallback
    if symbols:
        requested = [s.strip().upper() for s in symbols.split(',')]
        filtered = {k: v for k, v in all_prices.items() if k.upper() in requested}
        if not filtered:
            raise HTTPException(404, detail={
                "error": f"No prices found for: {symbols}",
                "hint": "Check symbol format.",
                "available_count": len(all_prices),
            })
        return _respond(filtered, 'prices', kd, ['yahoo_finance'])
    return _respond(all_prices, 'prices', kd, ['yahoo_finance'])


@app.get("/v1/prices/history", tags=["Market"],
    summary="365-Day Price History",
    description=(
        "Historical daily prices for the last 365 days for a specific symbol. "
        "Use this for technical analysis, backtesting, or trend detection.\n\n"
        "Example: `/v1/prices/history?symbol=AAPL`"
    ),
    operation_id="getPriceHistory",
)
async def prices_history(
    x_api_key: str = Header(None, alias="X-API-Key"),
    symbol: str = Query(..., description="Ticker symbol. Example: AAPL, MSFT, GC=F"),
):
    kd = _auth(x_api_key, 'prices')
    history = _load_json('prices_history.json', {})
    sym_data = history.get(symbol.upper(), history.get(symbol, None))
    if not sym_data:
        raise HTTPException(404, detail={
            "error": f"No price history for {symbol}",
            "hint": "Check the symbol format. Use GET /v1/prices to see all tracked symbols.",
        })
    return _respond({'symbol': symbol.upper(), 'history': sym_data}, 'prices', kd, ['yahoo_finance'])


@app.get("/v1/analysis/{ticker}", tags=["Analysis"],
    summary="Deep AI Stock Analysis",
    description=(
        "Comprehensive AI-generated analysis for a specific stock or asset. "
        "Includes fundamentals (P/E, revenue, margins), technicals, and AI assessment.\n\n"
        "NOT available for all tickers — only assets that have been analyzed. "
        "If analysis is not available, the response will include a 404 with hints."
    ),
    operation_id="getStockAnalysis",
)
async def stock_analysis(
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    kd = _auth(x_api_key, 'analysis')
    analyses = _load_json('stock_analyses.json', {})
    result = analyses.get(ticker.upper()) or analyses.get(ticker.lower()) or analyses.get(ticker)
    if not result:
        fund = _load_json('fundamentals_cache.json', {})
        result = fund.get(ticker.upper()) or fund.get(ticker.lower())
    if not result:
        raise HTTPException(404, detail={
            "error": f"No analysis available for {ticker}",
            "hint": "Try common tickers like AAPL, MSFT, TSLA. Use /v1/signals/latest to see which assets have active signals.",
        })
    return _respond(result, 'analysis', kd, ['yahoo_finance', 'fundamentals', 'claude_analysis'])


@app.get("/v1/portfolio/model", tags=["Portfolio"],
    summary="Model Portfolio Positions",
    description=(
        "Current positions and performance of the NORTH7 model portfolio. "
        "Shows what the AI system is currently holding with direction and performance."
    ),
    operation_id="getModelPortfolio",
)
async def model_portfolio(x_api_key: str = Header(None, alias="X-API-Key")):
    kd = _auth(x_api_key, 'portfolio')
    portfolio = _load_json('portfolio.json', {})
    performance = _load_json('performance.json', {})

    # Redact sensitive data: no entry_price, no exact position sizes
    redacted_positions = []
    positions = portfolio.get('positions', portfolio.get('open', []))
    if isinstance(positions, list):
        for pos in positions:
            redacted_positions.append({
                'symbol': pos.get('symbol', pos.get('ticker', '')),
                'direction': pos.get('direction', 'long'),
                'performance_pct': pos.get('pnl_pct', pos.get('performance_pct', pos.get('unrealized_pnl_pct', 0))),
            })
    elif isinstance(positions, dict):
        for sym, pos in positions.items():
            if isinstance(pos, dict):
                redacted_positions.append({
                    'symbol': sym,
                    'direction': pos.get('direction', 'long'),
                    'performance_pct': pos.get('pnl_pct', pos.get('performance_pct', pos.get('unrealized_pnl_pct', 0))),
                })

    # Redact performance: only summary, no position-level details
    redacted_performance = {}
    if isinstance(performance, dict):
        redacted_performance = {
            'total_return_pct': performance.get('total_return_pct', performance.get('return_pct', 0)),
            'position_count': len(redacted_positions),
            'updated': performance.get('updated', performance.get('as_of', '')),
        }

    return _respond(
        {'portfolio': {'positions': redacted_positions}, 'performance': redacted_performance},
        'portfolio', kd, ['portfolio_engine', 'yahoo_finance']
    )


@app.get("/v1/intelligence/briefing", tags=["Intelligence"],
    summary="Daily Intelligence Briefing",
    description=(
        "AI-generated daily market intelligence briefing covering geopolitical events, "
        "market-moving news, and forward-looking analysis. Available in English and German.\n\n"
        "Updated daily. Use `lang=de` for German, `lang=en` (default) for English."
    ),
    operation_id="getIntelligenceBriefing",
)
async def intelligence_briefing(
    x_api_key: str = Header(None, alias="X-API-Key"),
    lang: str = Query('en', description="Language: 'en' for English (default), 'de' for German."),
):
    kd = _auth(x_api_key, 'intelligence')
    if lang == 'de':
        daily = _load_json('daily_de.json', {})
    else:
        daily = _load_json('daily_en.json', _load_json('daily.json', {}))
    return _respond(daily, 'intelligence', kd, ['gdelt', 'claude_analysis', 'news'])


@app.get("/v1/sector-radar", tags=["Analysis"],
    summary="Sector Rotation Radar",
    description=(
        "Sector rotation analysis showing breadth and momentum across market sectors. "
        "Identifies which sectors are leading or lagging the broader market.\n\n"
        "Use this to identify sector trends and rotate into strong sectors."
    ),
    operation_id="getSectorRadar",
)
async def sector_radar(x_api_key: str = Header(None, alias="X-API-Key")):
    kd = _auth(x_api_key, 'sector_radar')
    radar = _load_json('sector_radar.json', {})
    return _respond(radar, 'sector_radar', kd, ['yahoo_finance', 'sp500_components'])


@app.get("/v1/commodities", tags=["Signals"],
    summary="Commodity Signals",
    description=(
        "AI scoring signals for 15 raw materials: gold, silver, oil, natural gas, "
        "wheat, corn, soybeans, coffee, cocoa, sugar, cotton, copper, platinum, palladium, lumber.\n\n"
        "Includes seasonal patterns and AI-generated scoring. Updated daily at 06:00 UTC."
    ),
    operation_id="getCommoditySignals",
)
async def commodities_signals(x_api_key: str = Header(None, alias="X-API-Key")):
    kd = _auth(x_api_key, 'commodities')
    scr = _load_json('scr.json', {})
    scr_en = _load_json('scr_en.json', {})
    return _respond({'scr': scr, 'translations': scr_en}, 'commodities', kd, ['commodity_scoring', 'seasonality'])




# ======================================================
# SUPPLY CHAIN RISK
# ======================================================

@app.get("/v1/supply-chain/risk", tags=["Supply Chain"],
    summary="Supply Chain Risk Radar",
    description=(
        "Real-time supply chain risk assessment for 37 commodities and energy carriers. "
        "Each commodity includes risk score (0-100), actionable recommendation (BUY/HOLD/HEDGE/AVOID), "
        "price forecast, worst/best case scenarios, and risk signals across 5 dimensions: "
        "geopolitics, weather, logistics, currency, and price trends.\n\n"
        "**Built for procurement teams, supply chain managers, and risk analysts.**\n\n"
        "Filter by commodity name or minimum risk score."
    ),
    operation_id="getSupplyChainRisk",
)
async def supply_chain_risk(
    x_api_key: str = Header(None, alias="X-API-Key"),
    commodity: Optional[str] = Query(None, description="Filter by commodity name, e.g. 'wheat', 'oil', 'coffee'. Case-insensitive partial match."),
    min_risk: Optional[int] = Query(None, description="Only return commodities with risk score >= this value (0-100)."),
    lang: str = Query("en", description="Language: 'en' for English, 'de' for German."),
):
    kd = _auth(x_api_key, 'commodities')
    scr = _load_json('scr_en.json' if lang == 'en' else 'scr.json', {})
    commodities = scr.get('commodities', [])

    results = []
    for c in commodities:
        # Filter by commodity name
        if commodity and commodity.lower() not in c.get('commodity', '').lower():
            continue
        # Filter by min risk
        if min_risk and c.get('risk_score', 0) < min_risk:
            continue

        decision = c.get('decision', {})
        impact = c.get('impact', {})
        szenarien = c.get('szenarien', {})
        signals = c.get('signals', {})
        trends = c.get('_trends_snapshot', {})
        price = c.get('_price_snapshot')

        results.append({
            'commodity': c.get('commodity'),
            'risk_score': c.get('risk_score'),
            'data_quality': c.get('data_quality'),
            'recommendation': {
                'action': decision.get('action', 'HOLD'),
                'detail': decision.get('empfehlung', decision.get('detail', '')),
            },
            'price': {
                'current': price,
                'forecast': impact.get('preis_prognose'),
                'forecast_period': impact.get('zeitraum'),
                'cost_risk': impact.get('kostenrisiko'),
                'trend_7d_pct': trends.get('7d') if isinstance(trends, dict) else None,
                'trend_14d_pct': trends.get('14d') if isinstance(trends, dict) else None,
                'trend_30d_pct': trends.get('30d') if isinstance(trends, dict) else None,
            },
            'scenarios': {
                'worst_case': szenarien.get('worst'),
                'best_case': szenarien.get('best'),
            },
            'risk_signals': {
                'geopolitics': signals.get('geopolitik'),
                'weather': signals.get('wetter'),
                'logistics': signals.get('logistik'),
                'currency': signals.get('waehrung'),
                'price_trend': signals.get('preistrend'),
            },
            'supply_delay_risk': impact.get('lieferverzoegerung'),
        })

    # Sort by risk score descending
    results.sort(key=lambda x: x.get('risk_score', 0), reverse=True)

    return _respond(
        {'commodities': results, 'count': len(results), 'total_tracked': len(commodities)},
        'commodities', kd, ['yahoo_finance', 'gdelt', 'open_meteo', 'news_feeds']
    )


@app.get("/v1/supply-chain/alerts", tags=["Supply Chain"],
    summary="Supply Chain Risk Alerts",
    description=(
        "Returns only HIGH RISK commodities (risk score >= 75). "
        "Use this endpoint for automated alerting — poll it periodically to detect "
        "emerging supply chain risks before they impact your operations."
    ),
    operation_id="getSupplyChainAlerts",
)
async def supply_chain_alerts(
    x_api_key: str = Header(None, alias="X-API-Key"),
    threshold: int = Query(75, description="Risk score threshold (default 75). Only commodities >= this score are returned."),
    lang: str = Query("en", description="Language: 'en' or 'de'."),
):
    kd = _auth(x_api_key, 'commodities')
    scr = _load_json('scr_en.json' if lang == 'en' else 'scr.json', {})
    commodities = scr.get('commodities', [])

    alerts = []
    for c in commodities:
        if c.get('risk_score', 0) >= threshold:
            decision = c.get('decision', {})
            impact = c.get('impact', {})
            alerts.append({
                'commodity': c.get('commodity'),
                'risk_score': c.get('risk_score'),
                'action': decision.get('action', 'MONITOR'),
                'recommendation': decision.get('empfehlung', ''),
                'price_forecast': impact.get('preis_prognose'),
                'cost_risk': impact.get('kostenrisiko'),
                'worst_case': c.get('szenarien', {}).get('worst'),
            })

    alerts.sort(key=lambda x: x.get('risk_score', 0), reverse=True)

    return _respond(
        {'alerts': alerts, 'count': len(alerts), 'threshold': threshold, 'total_tracked': len(commodities)},
        'commodities', kd, ['yahoo_finance', 'gdelt', 'open_meteo']
    )


@app.get("/v1/intraday", tags=["Signals"],
    summary="Intraday Momentum Scanner",
    description=(
        "Intraday momentum signals updated every 30 minutes during market hours (Mon-Fri 08:00-21:00 UTC). "
        "Scans for short-term momentum breakouts and reversals.\n\n"
        "**Warning:** Intraday signals are time-sensitive. Check the `updated` timestamp "
        "and discard signals older than 1 hour."
    ),
    operation_id="getIntradayScanner",
)
async def intraday_scanner(x_api_key: str = Header(None, alias="X-API-Key")):
    kd = _auth(x_api_key, 'intraday')
    scanner = _load_json('intraday_scanner.json', {})
    return _respond(scanner, 'intraday', kd, ['yahoo_finance', 'momentum_scanner'])


# ══════════════════════════════════════════════════
# ACCOUNT
# ══════════════════════════════════════════════════

@app.get("/v1/account", tags=["Account"],
    summary="API Key Status",
    description="Check your API key status, remaining credits, and usage statistics. No credits deducted.",
    operation_id="getAccountInfo",
)
async def account_info(x_api_key: str = Header(None, alias="X-API-Key")):
    if not x_api_key:
        raise HTTPException(401, detail={
            "error": "Missing X-API-Key header",
            "hint": "Pass your API key to check your account status.",
        })
    info = get_key_info(x_api_key)
    if not info:
        raise HTTPException(401, detail={"error": "Unknown API key", "hint": "Check that your key starts with 'n7_live_'."})
    safe = {
        'name': info['name'],
        'tier': info['tier'],
        'credits': info['credits'],
        'rate_limit': info['rate_limit'],
        'total_requests': info['total_requests'],
        'total_cost_credits': info.get('total_cost_credits', 0),
        'created_utc': info['created_utc'],
        'last_used_utc': info.get('last_used_utc'),
        'active': info.get('active', True),
    }
    return N7Response(ok=True, data=safe, meta={'endpoint': 'account'})



# ======================================================
# CHECKOUT (PayPal self-service)
# ======================================================

@app.post("/v1/checkout/create", tags=["Checkout"],
    summary="Create PayPal Order",
    description="Start a PayPal payment to purchase API credits.",
    operation_id="createCheckoutOrder",
)
async def checkout_create(
    tier: str = Query(..., description="Tier: starter (5 EUR) or pro (25 EUR)"),
    email: str = Query("", description="Your email"),
):
    from api.v1.checkout import create_order
    result = create_order(tier, email)
    if "error" in result:
        raise HTTPException(400, detail=result["error"])
    return result


@app.post("/v1/checkout/capture", tags=["Checkout"],
    summary="Capture PayPal Payment & Get API Key",
    description="After PayPal approval, capture payment and receive your API key.",
    operation_id="captureCheckoutOrder",
)
async def checkout_capture(
    order_id: str = Query(..., description="PayPal order ID"),
    name: str = Query("", description="Name for your API key"),
    email: str = Query("", description="Your email"),
):
    from api.v1.checkout import capture_order
    result = capture_order(order_id, name, email)
    if "error" in result:
        raise HTTPException(400, detail=result["error"])
    return result


@app.get("/v1/checkout/tiers", tags=["Checkout"],
    summary="Available Tiers & Pricing",
    description="List tiers and pricing. No auth required.",
    operation_id="getCheckoutTiers",
)
async def checkout_tiers():
    from api.v1.checkout import TIERS
    return {
        "ok": True,
        "tiers": {k: {"credits": v["credits"], "price": v["price"], "currency": v["currency"], "rate_limit": v["rate_limit"]} for k, v in TIERS.items()},
        "free": {"credits": 1000, "price": "0", "note": "Instant — no payment needed"},
    }


@app.post("/v1/checkout/free", tags=["Checkout"],
    summary="Get Free API Key (1,000 credits)",
    description=(
        "Get a free API key instantly with 1,000 credits. No payment required. "
        "Perfect for testing and evaluating the API. "
        "Rate limit: 10 requests/minute. One free key per email."
    ),
    operation_id="getFreeApiKey",
)
async def checkout_free(
    email: str = Query(..., description="Your email address (required, one free key per email)"),
    name: str = Query("", description="Name for your API key"),
):
    if not email or "@" not in email or "." not in email:
        raise HTTPException(400, detail={"error": "Valid email required", "hint": "Provide a real email address."})
    # Check if this email already has a free key
    from api.v1.auth import list_all_keys, create_api_key
    keys = list_all_keys()
    for k, v in keys.items():
        if v.get("owner_email", "").lower() == email.lower() and v.get("tier") == "free":
            raise HTTPException(409, detail={
                "error": "Free key already exists for this email",
                "hint": "You already have a free API key. Upgrade to Starter (5 EUR) or Pro (25 EUR) for more credits.",
            })
    key_name = name or email.split("@")[0]
    api_key, key_data = create_api_key(key_name, email, "free")
    # Telegram notification
    try:
        from api.telegram_notify import send as send_telegram
        send_telegram(f"\U0001f511 Neuer FREE API Key!\nEmail: {email}\nName: {key_name}\nCredits: 1,000")
    except Exception:
        pass
    return {
        "ok": True,
        "api_key": api_key,
        "tier": "free",
        "credits": 1000,
        "rate_limit": 10,
        "name": key_name,
        "message": "Your free API key is ready! Store it securely — it cannot be retrieved later.",
    }


# ══════════════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════════════

@app.post("/v1/admin/keys", tags=["Admin"],
    summary="Create API Key",
    description="Admin: Create a new API key for a developer or agent. Requires X-Admin-Token.",
    operation_id="adminCreateKey",
)
async def admin_create_key(
    name: str = Query(..., description="Name for the key, e.g. 'My Trading Agent'"),
    email: str = Query(..., description="Owner email for billing and notifications"),
    tier: str = Query('free', description="Tier: free, starter, pro, enterprise"),
    x_admin_token: str = Header(None, alias="X-Admin-Token"),
):
    _admin_check(x_admin_token)
    key, data = create_api_key(name, email, tier)
    return {
        'ok': True,
        'api_key': key,
        'name': data['name'],
        'tier': data['tier'],
        'credits': data['credits'],
        'rate_limit': data['rate_limit'],
        'message': 'Store this key securely. It cannot be retrieved later.',
    }


@app.post("/v1/admin/credits", tags=["Admin"],
    summary="Add Credits",
    description="Admin: Add credits to an existing API key.",
    operation_id="adminAddCredits",
)
async def admin_add_credits(
    api_key: str = Query(..., description="The full API key to add credits to"),
    amount: int = Query(..., description="Number of credits to add"),
    x_admin_token: str = Header(None, alias="X-Admin-Token"),
):
    _admin_check(x_admin_token)
    result = add_credits(api_key, amount)
    if not result:
        raise HTTPException(404, detail="API key not found")
    return {'ok': True, 'credits': result['credits'], 'name': result['name']}


@app.get("/v1/admin/keys", tags=["Admin"],
    summary="List All Keys",
    operation_id="adminListKeys",
)
async def admin_list_keys(x_admin_token: str = Header(None, alias="X-Admin-Token")):
    _admin_check(x_admin_token)
    keys = list_all_keys()
    summary = []
    for k, v in keys.items():
        summary.append({
            'key_prefix': k[:16] + '...',
            'name': v['name'],
            'tier': v['tier'],
            'credits': v['credits'],
            'total_requests': v['total_requests'],
            'active': v.get('active', True),
            'last_used_utc': v.get('last_used_utc'),
        })
    return {'ok': True, 'keys': summary, 'count': len(summary)}


@app.get("/v1/admin/usage", tags=["Admin"],
    summary="Usage Log",
    operation_id="adminUsageLog",
)
async def admin_usage(
    x_admin_token: str = Header(None, alias="X-Admin-Token"),
    limit: int = Query(100, le=1000),
):
    _admin_check(x_admin_token)
    from api.v1.auth import _load_usage
    usage = _load_usage()
    return {'ok': True, 'entries': usage[-limit:], 'total': len(usage)}


# ══════════════════════════════════════════════════
# META / DISCOVERY
# ══════════════════════════════════════════════════

@app.get("/v1/", tags=["Free"],
    summary="API Overview",
    description=(
        "Complete API overview with all endpoints, pricing, and integration methods. "
        "**NO API KEY REQUIRED.** This is the starting point for any agent discovering NORTH7."
    ),
    operation_id="getApiOverview",
)
async def api_info():
    return {
        'name': 'NORTH7 Agent API',
        'version': '1.0.0',
        'tagline': 'Financial intelligence infrastructure for AI agents',
        'description': 'AI-analyzed trading signals, risk assessment, and decision intelligence — not raw data. Built for autonomous agents.',
        'agent_instructions': AGENT_INSTRUCTIONS,
        'free_endpoints': {
            '/v1/risk': {'cost': 0, 'desc': 'Global risk index 0-100 with crises and regional breakdown', 'safe': True},
            '/v1/regime': {'cost': 0, 'desc': 'Market regime: BULL / BEAR / SIDEWAYS / CRISIS', 'safe': True},
            '/v1/health': {'cost': 0, 'desc': 'API health, data freshness, integration URLs', 'safe': True},
        },
        'authenticated_endpoints': {
            '/v1/signals/latest': {'cost': 1, 'desc': 'All trading signals from 6 AI sources'},
            '/v1/signals/alpha': {'cost': 2, 'desc': 'Alpha Daily — highest-conviction opportunities'},
            '/v1/prices': {'cost': 1, 'desc': 'Real-time prices for 80+ assets'},
            '/v1/prices/history': {'cost': 1, 'desc': '365-day price history per symbol'},
            '/v1/analysis/{ticker}': {'cost': 5, 'desc': 'Deep AI stock analysis with fundamentals'},
            '/v1/portfolio/model': {'cost': 10, 'desc': 'Model portfolio positions + performance'},
            '/v1/intelligence/briefing': {'cost': 10, 'desc': 'Daily geopolitical intelligence briefing'},
            '/v1/sector-radar': {'cost': 2, 'desc': 'Sector rotation radar'},
            '/v1/commodities': {'cost': 2, 'desc': 'Commodity signals (15 raw materials)'},
            '/v1/intraday': {'cost': 2, 'desc': 'Intraday momentum scanner'},
            '/v1/account': {'cost': 0, 'desc': 'Your API key status + credits'},
        },
        'auth': {
            'method': 'API key via X-API-Key header',
            'key_format': 'n7_live_<hex32>',
            'get_key': 'Contact support@north7.ai for a free key (1,000 credits)',
        },
        'integration': {
            'rest_api': 'https://north7.ai/v1/',
            'mcp_server': 'https://north7.ai/mcp',
            'openapi_spec': 'https://north7.ai/v1/openapi.json',
            'swagger_docs': 'https://north7.ai/v1/docs',
            'agent_card': 'https://north7.ai/.well-known/agent.json',
            'ai_plugin': 'https://north7.ai/.well-known/ai-plugin.json',
        },
        'pricing': {
            'free': {'credits': 1000, 'rate_limit': '10/min', 'price': 'Free'},
            'starter': {'credits': 50000, 'rate_limit': '60/min', 'price': '5 EUR'},
            'pro': {'credits': 500000, 'rate_limit': '300/min', 'price': '25 EUR'},
            'enterprise': {'credits': 'unlimited', 'rate_limit': '1000/min', 'price': 'Contact us'},
        },
        'data_sources': [
            'Yahoo Finance (prices, fundamentals)',
            'GDELT (geopolitical events)',
            'USGS (seismic data)',
            'Climate/weather feeds',
            'Claude AI (signal analysis, briefings)',
        ],
        'unique_value': 'Unlike raw data APIs, NORTH7 delivers AI-analyzed DECISION INTELLIGENCE with confidence scores and reasoning.',
    }
