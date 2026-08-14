"""API Key authentication and credit management for NORTH7 Agent API v1.

Storage: /home/developer/north7/data/api_keys.json
Format:
{
  "n7_live_xxxxxxxx": {
    "name": "My Trading Agent",
    "owner_email": "dev@example.com",
    "credits": 9500,
    "tier": "starter",          # starter / pro / enterprise
    "rate_limit": 60,           # requests per minute
    "created_utc": "...",
    "last_used_utc": "...",
    "total_requests": 142,
    "total_cost_cents": 5.0,
    "active": true
  }
}

Usage log: /home/developer/north7/data/api_usage.json
"""
from __future__ import annotations

import json
import os
import hmac
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
KEYS_FILE = os.path.join(DATA_DIR, 'api_keys.json')
USAGE_FILE = os.path.join(DATA_DIR, 'api_usage.json')

_lock = threading.Lock()

# ── Tier definitions ──
TIERS = {
    'free':       {'credits': 1000,   'rate_limit': 10,  'price_eur': 0},
    'starter':    {'credits': 50000,  'rate_limit': 60,  'price_eur': 5},
    'pro':        {'credits': 500000, 'rate_limit': 300, 'price_eur': 25},
    'enterprise': {'credits': -1,     'rate_limit': 1000, 'price_eur': 0},  # unlimited
}

# ── Cost per endpoint (in credits, 1 credit ≈ 0.001 cent) ──
ENDPOINT_COSTS = {
    'signals_latest':   1,
    'signals_alpha':    2,
    'risk':             1,
    'regime':           1,
    'prices':           1,
    'analysis':         5,
    'portfolio':       10,
    'intelligence':    10,
    'decision':        20,
    'sector_radar':     2,
    'commodities':      2,
    'intraday':         2,
}

# ── Telegram notification state (in-memory) ──
_seen_keys: set[str] = set()           # keys that have been seen this session
_seen_keys_lock = threading.Lock()


def _telegram_notify_async(text: str):
    """Send Telegram notification in background thread. Never blocks API."""
    def _send():
        try:
            import sys
            api_dir = os.path.join(os.path.dirname(__file__), '..')
            if api_dir not in sys.path:
                sys.path.insert(0, api_dir)
            from telegram_notify import send
            send(text)
        except Exception:
            pass  # fail-silent
    threading.Thread(target=_send, daemon=True).start()


def _notify_api_usage(api_key: str, endpoint: str, key_data: dict):
    """Send Telegram notification for notable API events:
    - First-time key usage (per server session)
    - Every 100th request of a key
    """
    from html import escape

    name = escape(str(key_data.get('name', '?')))
    tier = escape(str(key_data.get('tier', '?')))
    total = key_data.get('total_requests', 0)
    credits_left = key_data.get('credits', 0)
    credits_str = 'unlimited' if credits_left == -1 else str(credits_left)

    with _seen_keys_lock:
        first_time = api_key not in _seen_keys
        if first_time:
            _seen_keys.add(api_key)

    # First-time usage this session
    if first_time:
        text = (
            f'\U0001f511 <b>NORTH7 API</b>\n'
            f'Key "<b>{name}</b>" ({tier}) connected\n'
            f'Endpoint: <code>{escape(endpoint)}</code>\n'
            f'Credits: {credits_str} | Total: {total} requests'
        )
        _telegram_notify_async(text)
        return

    # Every 100th request milestone
    if total > 0 and total % 100 == 0:
        text = (
            f'\U0001f4ca <b>NORTH7 API Milestone</b>\n'
            f'Key "<b>{name}</b>" ({tier}) — {total} requests\n'
            f'Latest: <code>{escape(endpoint)}</code>\n'
            f'Credits remaining: {credits_str}'
        )
        _telegram_notify_async(text)


def _load_keys() -> dict:
    if not os.path.exists(KEYS_FILE):
        return {}
    with open(KEYS_FILE) as f:
        return json.load(f)


def _save_keys(keys: dict):
    tmp = KEYS_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(keys, f, indent=2, ensure_ascii=False)
    os.replace(tmp, KEYS_FILE)


def _load_usage() -> list:
    if not os.path.exists(USAGE_FILE):
        return []
    with open(USAGE_FILE) as f:
        return json.load(f)


def _append_usage(entry: dict):
    """Append usage entry. Keep last 100k entries max."""
    with _lock:
        usage = _load_usage()
        usage.append(entry)
        if len(usage) > 100_000:
            usage = usage[-100_000:]
        tmp = USAGE_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(usage, f, ensure_ascii=False)
        os.replace(tmp, USAGE_FILE)


# ── Rate limiter (in-memory, sliding window) ──
_rate_windows: dict[str, list[float]] = {}
_rate_lock = threading.Lock()


def _check_rate_limit(api_key: str, limit: int) -> bool:
    """Returns True if request is allowed."""
    now = time.time()
    with _rate_lock:
        window = _rate_windows.get(api_key, [])
        # Remove entries older than 60s
        window = [t for t in window if now - t < 60]
        if len(window) >= limit:
            return False
        window.append(now)
        _rate_windows[api_key] = window
        return True


def create_api_key(name: str, owner_email: str, tier: str = 'free') -> tuple[str, dict]:
    """Create a new API key. Returns (key_string, key_data)."""
    if tier not in TIERS:
        tier = 'free'
    token = f"n7_live_{secrets.token_hex(16)}"
    now = datetime.now(timezone.utc).isoformat()
    key_data = {
        'name': name,
        'owner_email': owner_email,
        'credits': TIERS[tier]['credits'],
        'tier': tier,
        'rate_limit': TIERS[tier]['rate_limit'],
        'created_utc': now,
        'last_used_utc': None,
        'total_requests': 0,
        'total_cost_credits': 0,
        'active': True,
    }
    with _lock:
        keys = _load_keys()
        keys[token] = key_data
        _save_keys(keys)
    return token, key_data


def validate_request(api_key: str, endpoint: str) -> tuple[bool, str, Optional[dict]]:
    """Validate an API request. Returns (ok, error_message, key_data)."""
    if not api_key or not api_key.startswith('n7_'):
        return False, 'Invalid API key format. Keys start with n7_', None

    with _lock:
        keys = _load_keys()
        key_data = keys.get(api_key)

    if not key_data:
        return False, 'Unknown API key', None

    if not key_data.get('active', True):
        return False, 'API key is deactivated', None

    # Check credits + rate limit + deduct atomically (single lock)
    cost = ENDPOINT_COSTS.get(endpoint, 1)
    if key_data['credits'] != -1 and key_data['credits'] < cost:
        return False, f'Insufficient credits. Need {cost}, have {key_data["credits"]}', key_data

    if not _check_rate_limit(api_key, key_data.get('rate_limit', 60)):
        return False, f'Rate limit exceeded ({key_data["rate_limit"]} req/min)', key_data

    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        keys = _load_keys()
        if api_key not in keys:
            return False, 'Unknown API key', None
        kd = keys[api_key]
        # Re-check credits inside lock (atomic)
        if kd['credits'] != -1:
            if kd['credits'] < cost:
                return False, f'Insufficient credits. Need {cost}, have {kd["credits"]}', kd
            kd['credits'] -= cost
        kd['last_used_utc'] = now
        kd['total_requests'] += 1
        kd['total_cost_credits'] = kd.get('total_cost_credits', 0) + cost
        _save_keys(keys)
        key_data = kd

    # Log usage async
    _append_usage({
        'key': api_key[:8] + '...',
        'endpoint': endpoint,
        'cost': cost,
        'ts': now,
    })

    # Telegram notification (async, non-blocking)
    _notify_api_usage(api_key, endpoint, key_data)

    return True, '', key_data


def get_key_info(api_key: str) -> Optional[dict]:
    """Get info for an API key (without exposing the full key)."""
    with _lock:
        keys = _load_keys()
        return keys.get(api_key)


def list_all_keys() -> dict:
    """Admin: list all keys."""
    with _lock:
        return _load_keys()


def add_credits(api_key: str, amount: int) -> Optional[dict]:
    """Add credits to a key."""
    with _lock:
        keys = _load_keys()
        if api_key not in keys:
            return None
        keys[api_key]['credits'] += amount
        _save_keys(keys)
        return keys[api_key]
