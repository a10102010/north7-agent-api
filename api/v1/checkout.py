"""PayPal Checkout for NORTH7 Agent API Credits.

Flow:
1. User clicks "Buy" on /developers page
2. PayPal JS SDK creates order via POST /v1/checkout/create
3. User approves payment in PayPal popup
4. PayPal JS SDK captures via POST /v1/checkout/capture
5. Server validates with PayPal API, creates API key, returns it
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.parse
import base64
import threading
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
CONFIG_ENV = os.path.join(os.path.dirname(__file__), '..', '..', 'config.env')

# Load PayPal credentials
_config = {}
if os.path.exists(CONFIG_ENV):
    with open(CONFIG_ENV) as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                _config[k.strip()] = v.strip()

PAYPAL_CLIENT_ID = _config.get('PAYPAL_CLIENT_ID', '')
PAYPAL_CLIENT_SECRET = _config.get('PAYPAL_CLIENT_SECRET', '')
PAYPAL_BASE = 'https://api-m.paypal.com'  # live

# Tier pricing
TIERS = {
    'starter': {'credits': 50000, 'price': '5.00', 'currency': 'EUR', 'rate_limit': 60},
    'pro':     {'credits': 500000, 'price': '25.00', 'currency': 'EUR', 'rate_limit': 300},
}

# Order tracking
ORDERS_FILE = os.path.join(DATA_DIR, 'api_paypal_orders.json')
_lock = threading.Lock()


def _load_orders() -> list:
    if not os.path.exists(ORDERS_FILE):
        return []
    try:
        with open(ORDERS_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_order(order: dict):
    with _lock:
        orders = _load_orders()
        orders.append(order)
        tmp = ORDERS_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(orders, f, indent=2, ensure_ascii=False)
        os.replace(tmp, ORDERS_FILE)


def _paypal_auth_header() -> str:
    creds = base64.b64encode(f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode()).decode()
    return f"Basic {creds}"


def _paypal_get_access_token() -> str:
    """Get OAuth2 access token from PayPal."""
    req = urllib.request.Request(
        f"{PAYPAL_BASE}/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": _paypal_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["access_token"]


def create_order(tier: str, email: str = '') -> dict:
    """Create a PayPal order for a tier."""
    if tier not in TIERS:
        return {'error': f'Unknown tier: {tier}. Available: {list(TIERS.keys())}'}

    t = TIERS[tier]
    token = _paypal_get_access_token()

    order_data = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {
                "currency_code": t['currency'],
                "value": t['price'],
            },
            "description": f"NORTH7 Agent API — {tier.upper()} ({t['credits']:,} credits)",
        }],
        "application_context": {
            "brand_name": "NORTH7",
            "landing_page": "NO_PREFERENCE",
            "user_action": "PAY_NOW",
            "return_url": "https://north7.ai/developers",
            "cancel_url": "https://north7.ai/developers",
        },
    }

    body = json.dumps(order_data).encode()
    req = urllib.request.Request(
        f"{PAYPAL_BASE}/v2/checkout/orders",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {'error': f'PayPal order creation failed ({e.code})', 'detail': body[:300]}

    # Track order
    _save_order({
        'paypal_order_id': result['id'],
        'tier': tier,
        'email': email,
        'price': t['price'],
        'currency': t['currency'],
        'credits': t['credits'],
        'status': 'CREATED',
        'created_utc': datetime.now(timezone.utc).isoformat(),
    })

    return {'order_id': result['id'], 'tier': tier, 'credits': t['credits']}


def capture_order(order_id: str, name: str = '', email: str = '') -> dict:
    """Capture a PayPal order and create API key."""
    token = _paypal_get_access_token()

    req = urllib.request.Request(
        f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture",
        data=b'',
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {'error': f'PayPal capture failed: {e.code}', 'detail': body[:200]}

    if result.get('status') != 'COMPLETED':
        return {'error': f'Payment not completed. Status: {result.get("status")}'}

    # Extract payer info
    payer = result.get('payer', {})
    payer_email = payer.get('email_address', email)
    payer_name = payer.get('name', {}).get('given_name', name) or name

    # Find the tier from our tracked orders
    orders = _load_orders()
    tier = 'starter'
    credits = 50000
    for o in orders:
        if o.get('paypal_order_id') == order_id:
            tier = o.get('tier', 'starter')
            credits = o.get('credits', 50000)
            o['status'] = 'COMPLETED'
            o['payer_email'] = payer_email
            o['captured_utc'] = datetime.now(timezone.utc).isoformat()
            break

    # Save updated orders
    with _lock:
        tmp = ORDERS_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(orders, f, indent=2, ensure_ascii=False)
        os.replace(tmp, ORDERS_FILE)

    # Create API key
    from api.v1.auth import create_api_key
    key_name = payer_name or f"PayPal-{order_id[:8]}"
    api_key, key_data = create_api_key(key_name, payer_email, tier)

    # Telegram notification
    try:
        from api.telegram_notify import send as send_telegram
        send_telegram(
            f"💰 API KEY VERKAUFT!\n"
            f"Tier: {tier.upper()}\n"
            f"Preis: {TIERS[tier]['price']} EUR\n"
            f"Credits: {credits:,}\n"
            f"Käufer: {payer_email}\n"
            f"Key: {api_key[:12]}...\n"
            f"PayPal Order: {order_id}"
        )
    except Exception:
        pass

    return {
        'ok': True,
        'api_key': api_key,
        'tier': tier,
        'credits': credits,
        'name': key_name,
        'email': payer_email,
        'message': 'Payment successful! Store your API key securely — it cannot be retrieved later.',
    }
