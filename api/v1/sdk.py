"""NORTH7 Python SDK — pip install north7 (future)

Usage:
    from north7 import North7
    
    n7 = North7("n7_live_your_key")
    
    signals = n7.signals()
    risk = n7.risk()
    regime = n7.regime()
    prices = n7.prices(["AAPL", "MSFT"])
    analysis = n7.analysis("TSLA")
    briefing = n7.briefing(lang="en")
    commodities = n7.commodities()
    portfolio = n7.portfolio()
    account = n7.account()
"""
from __future__ import annotations

try:
    import requests as _requests
except ImportError:
    import urllib.request
    import json as _json

    class _MinimalHTTP:
        """Fallback if requests is not installed."""
        def get(self, url, headers=None):
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req) as resp:
                return type('R', (), {'json': lambda self=resp: _json.loads(self.read()), 'status_code': resp.status})()
    _requests = _MinimalHTTP()


class North7Error(Exception):
    def __init__(self, message: str, code: int = 0):
        self.message = message
        self.code = code
        super().__init__(message)


class North7:
    """NORTH7 Agent API client.
    
    Args:
        api_key: Your API key (starts with n7_live_)
        base_url: API base URL (default: https://north7.ai/v1)
    """
    
    def __init__(self, api_key: str, base_url: str = "https://north7.ai/v1"):
        if not api_key or not api_key.startswith("n7_"):
            raise North7Error("Invalid API key. Keys start with n7_")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key}

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{self.base_url}{path}"
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
            if qs:
                url += f"?{qs}"
        resp = _requests.get(url, headers=self._headers)
        data = resp.json()
        if not data.get("ok", True) or "detail" in data:
            raise North7Error(data.get("detail", data.get("error", "Unknown error")), resp.status_code)
        return data

    def signals(self, source: str = None) -> dict:
        """Get trading signals. source: news_5m, alpha_14d, radar_daily, intraday_30m, scr_daily"""
        return self._get("/signals/latest", {"source": source})

    def alpha(self) -> dict:
        """Get Alpha Daily signals."""
        return self._get("/signals/alpha")

    def risk(self) -> dict:
        """Get global risk index (0-100)."""
        return self._get("/risk")

    def regime(self) -> dict:
        """Get market regime (BULL/BEAR/SIDEWAYS/CRISIS)."""
        return self._get("/regime")

    def prices(self, symbols: list[str] = None) -> dict:
        """Get real-time prices. symbols: list of tickers or None for all."""
        params = {}
        if symbols:
            params["symbols"] = ",".join(symbols)
        return self._get("/prices", params)

    def price_history(self, symbol: str) -> dict:
        """Get 365-day price history for a symbol."""
        return self._get("/prices/history", {"symbol": symbol})

    def analysis(self, ticker: str) -> dict:
        """Get deep AI analysis for a stock."""
        return self._get(f"/analysis/{ticker}")

    def portfolio(self) -> dict:
        """Get model portfolio."""
        return self._get("/portfolio/model")

    def briefing(self, lang: str = "en") -> dict:
        """Get daily intelligence briefing. lang: en or de."""
        return self._get("/intelligence/briefing", {"lang": lang})

    def sector_radar(self) -> dict:
        """Get sector rotation radar."""
        return self._get("/sector-radar")

    def commodities(self) -> dict:
        """Get commodity signals."""
        return self._get("/commodities")

    def intraday(self) -> dict:
        """Get intraday scanner results."""
        return self._get("/intraday")

    def account(self) -> dict:
        """Get API key status and remaining credits."""
        return self._get("/account")


# ── Quick test ──
if __name__ == "__main__":
    import sys
    key = sys.argv[1] if len(sys.argv) > 1 else None
    if not key:
        print("Usage: python3 sdk.py <api_key>")
        sys.exit(1)
    
    n7 = North7(key)
    
    print("=== Risk Index ===")
    r = n7.risk()
    print(f"  Risk: {r['data']['value']}/100 ({r['data']['status']})")
    
    print("\n=== Market Regime ===")
    r = n7.regime()
    print(f"  Regime: {r['data']['regime']}")
    
    print("\n=== Signals ===")
    r = n7.signals()
    print(f"  {r['data']['count']} signals")
    
    print("\n=== Account ===")
    r = n7.account()
    print(f"  Credits: {r['data']['credits']}")
    print(f"  Requests: {r['data']['total_requests']}")
