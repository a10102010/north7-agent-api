# NORTH7 — Global AI Infrastructure for Finance & Security

**Financial intelligence API for autonomous AI agents.** Real-time market signals, risk assessment, regime detection, and geopolitical early warning — built for machines, readable by humans.

[![API Status](https://img.shields.io/badge/API-Live-brightgreen)](https://north7.ai/v1/health)
[![MCP](https://img.shields.io/badge/MCP-Compatible-blue)](https://north7.ai/mcp)
[![Endpoints](https://img.shields.io/badge/Endpoints-12-blue)](https://north7.ai/v1/docs)
[![Free Tier](https://img.shields.io/badge/Free_Tier-1000_credits-green)](https://north7.ai/developers)

---

## Quick Start

**No API key needed** — try it now:

```bash
# Global risk index (0-100)
curl https://north7.ai/v1/risk

# Market regime (BULL/BEAR/SIDEWAYS/CRISIS)
curl https://north7.ai/v1/regime
```

**Get a free API key** (1,000 credits, instant):

```bash
curl -X POST "https://north7.ai/v1/checkout/free?email=you@example.com&name=MyAgent"
```

**Use your key:**

```bash
curl https://north7.ai/v1/signals/latest -H "X-API-Key: n7_live_your_key"
```

---

## What Makes This Different

| Standard Financial APIs | NORTH7 |
|------------------------|--------|
| Raw price data (OHLCV) | AI-analyzed signals with confidence + reasoning |
| Requires API key to try | 3 free endpoints — try instantly |
| Built for human developers | Agent-native: MCP, A2A, rich error hints |
| Single asset class | Multi-asset: stocks, commodities, forex |
| No context | Geopolitics + regime + risk integrated |
| Just data | Decision intelligence: "what to do" not "what happened" |

---

## Endpoints

### Free (no API key)

| Endpoint | Description |
|----------|-------------|
| `GET /v1/risk` | Global risk index 0-100 + active crises + regional breakdown |
| `GET /v1/regime` | Market regime: BULL / BEAR / SIDEWAYS / CRISIS |
| `GET /v1/health` | API status + data freshness |

### Authenticated (API key required)

| Endpoint | Credits | Description |
|----------|---------|-------------|
| `GET /v1/signals/latest` | 1 | All trading signals from 6 AI sources |
| `GET /v1/signals/alpha` | 2 | Alpha Daily — highest conviction opportunities |
| `GET /v1/prices` | 1 | Real-time prices for 80+ assets |
| `GET /v1/prices/history` | 1 | 365-day price history |
| `GET /v1/analysis/{ticker}` | 5 | Deep AI stock analysis |
| `GET /v1/sector-radar` | 2 | Sector rotation radar |
| `GET /v1/commodities` | 2 | Commodity signals (15 raw materials) |
| `GET /v1/intraday` | 2 | Intraday momentum scanner |
| `GET /v1/intelligence/briefing` | 10 | Daily geopolitical briefing |
| `GET /v1/portfolio/model` | 10 | Model portfolio positions |

---

## Integration

### Python

```python
import requests

# No key needed
risk = requests.get("https://north7.ai/v1/risk").json()
print(f"Risk: {risk['data']['value']}/100 ({risk['data']['status']})")

# With key
headers = {"X-API-Key": "n7_live_your_key"}
signals = requests.get("https://north7.ai/v1/signals/latest", headers=headers).json()
print(f"{signals['data']['count']} signals found")
```

### MCP (Model Context Protocol)

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "north7": {
      "url": "https://north7.ai/mcp",
      "transport": "streamable-http"
    }
  }
}
```

9 tools available: `get_trading_signals`, `get_risk_index`, `get_market_regime`, `get_prices`, `get_stock_analysis`, `get_intelligence_briefing`, `get_commodity_signals`, `get_sector_radar`, `get_model_portfolio`

### A2A (Agent-to-Agent)

```bash
curl https://north7.ai/.well-known/agent.json
```

### OpenAPI

```bash
curl https://north7.ai/v1/openapi.json
```

Interactive docs: [north7.ai/v1/docs](https://north7.ai/v1/docs)

---

## Pricing

| Tier | Credits | Price | Rate Limit |
|------|---------|-------|------------|
| **Free** | 1,000 | Free | 10 req/min |
| **Starter** | 50,000 | €5 | 60 req/min |
| **Pro** | 500,000 | €25 | 300 req/min |
| **Enterprise** | Unlimited | Custom | 1,000 req/min |

---

## Three Pillars

### 1. AI Agent Infrastructure
Financial intelligence API for autonomous AI agents worldwide. MCP + A2A + OpenAPI compatible.

### 2. Trading Intelligence
AI-powered trading with autonomous agents. Multi-asset: stocks, commodities, forex.

### 3. Geopolitical Early Warning
OSINT-powered risk analysis. 1,071 verified predictions with 52.2% calibrated accuracy.

---

## Links

| Resource | URL |
|----------|-----|
| Developer Page | [north7.ai/developers](https://north7.ai/developers) |
| API Docs (Swagger) | [north7.ai/v1/docs](https://north7.ai/v1/docs) |
| OpenAPI Spec | [north7.ai/v1/openapi.json](https://north7.ai/v1/openapi.json) |
| MCP Server | [north7.ai/mcp](https://north7.ai/mcp) |
| Agent Discovery | [north7.ai/.well-known/agent.json](https://north7.ai/.well-known/agent.json) |
| AI Plugin | [north7.ai/.well-known/ai-plugin.json](https://north7.ai/.well-known/ai-plugin.json) |
| Website | [north7.at](https://north7.at) |
| Track Record | [north7.ai/intelligence-track-record](https://north7.ai/intelligence-track-record) |

---

**Built in Austria.**

© 2024–2026 NORTH7
