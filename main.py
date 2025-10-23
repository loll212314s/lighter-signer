import os, json, asyncio, logging, urllib.request, urllib.error
from flask import Flask, request, jsonify
import lighter  # from requirements.txt

# tame noisy logs
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.INFO)

app = Flask(__name__)

BASE_URL       = os.environ.get("BASE_URL", "https://mainnet.zklighter.elliot.ai").rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
API_PRIV       = os.environ.get("API_KEY_PRIVATE_KEY") or os.environ.get("LIGHTER_PRIVATE_KEY")
ACCOUNT_INDEX  = int(os.environ.get("ACCOUNT_INDEX", "0"))
API_KEY_INDEX  = int(os.environ.get("API_KEY_INDEX", "0"))

_CLIENTS_KEY = "_lighter_clients"
_MARKET_CACHE = "_market_index_cache"

def _http_json(path: str):
    """GET JSON from Lighter REST, try both markets endpoints."""
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

def resolve_market_index(symbol: str) -> int:
    """Return numeric market index for a symbol like 'BTC-USDC' or 'BTC_USDC'."""
    sym = symbol.upper().replace("_", "-")
    cache = app.config.get(_MARKET_CACHE, {})
    if sym in cache:
        return cache[sym]

    # try the common endpoints
    for path in ("/api/v1/markets", "/api/v1/getMarkets"):
        try:
            data = _http_json(path)
        except Exception:
            continue

        markets = data.get("markets", data)
        if isinstance(markets, list):
            for m in markets:
                ms = (m.get("symbol") or m.get("name") or "").upper().replace("_", "-")
                if ms == sym:
                    idx = m.get("market_index", m.get("index", m.get("id")))
                    if idx is None:
                        continue
                    idx = int(idx)
                    cache[sym] = idx
                    app.config[_MARKET_CACHE] = cache
                    return idx

    # fallback: let caller see a clear error
    raise ValueError(f"Could not resolve market index for {sym}")

async def _make_clients_async():
    signer = lighter.SignerClient(
        url=BASE_URL,
        private_key=API_PRIV,
        account_index=ACCOUNT_INDEX,
        api_key_index=API_KEY_INDEX,
    )
    cfg = lighter.Configuration(host=BASE_URL)
    api_client = lighter.ApiClient(configuration=cfg)
    tx_api = lighter.TransactionApi(api_client)
    return signer, tx_api

def get_clients():
    clients = app.config.get(_CLIENTS_KEY)
    if clients is not None:
        return clients
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if not loop.is_running():
        clients = loop.run_until_complete(_make_clients_async())
    else:
        fut = asyncio.run_coroutine_threadsafe(_make_clients_async(), loop)
        clients = fut.result()
    app.config[_CLIENTS_KEY] = clients
    return clients

@app.get("/")
def root():
    return jsonify({"status": "ok"})

@app.post("/webhook")
def webhook():
    body = request.get_json(force=True, silent=True) or {}
    if WEBHOOK_SECRET and body.get("secret") != WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "bad secret"}), 401

    # inputs
    symbol = str(body.get("symbol", "BTC-USDC"))
    side   = str(body.get("side", "buy")).lower()
    qty    = float(str(body.get("qty", "0.0001")))
    base_amount = int(qty * 1_0000_0000)  # example 1e8 scale

    try:
        market_index = resolve_market_index(symbol)
    except Exception as e:
        return jsonify({"ok": False, "error": f"market lookup failed: {e}"}), 400

    signer, tx_api = get_clients()

    # POSitional args (SDK requires these), include reduce_only & trigger_price
    signed_tx = signer.sign_create_order(
        market_index,                              # <-- numeric market index
        side,                                      # "buy"/"sell"
        base_amount,                               # int
        0,                                         # price (0 = market)
        0,                                         # client_order_index
        "ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL",
        "ORDER_TYPE_MARKET",
        False,                                     # reduce_only
        0,                                         # trigger_price
    )

    resp = tx_api.send_tx(signed_tx)
    print("Lighter send_tx response:", resp, flush=True)
    return jsonify({"ok": True, "lighter_response": resp})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print("URL MAP:", app.url_map, flush=True)
    app.run(host="0.0.0.0", port=port)
