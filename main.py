import os, json, asyncio, logging
from flask import Flask, request, jsonify
import lighter  # from requirements.txt (lighter-python)

# --- tame the log spam ---
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.INFO)

app = Flask(__name__)

BASE_URL       = os.environ.get("BASE_URL", "https://mainnet.zklighter.elliot.ai")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
API_PRIV       = os.environ.get("API_KEY_PRIVATE_KEY") or os.environ.get("LIGHTER_PRIVATE_KEY")
ACCOUNT_INDEX  = int(os.environ.get("ACCOUNT_INDEX", "0"))
API_KEY_INDEX  = int(os.environ.get("API_KEY_INDEX", "0"))

_CLIENTS_KEY = "_lighter_clients"

async def _make_clients_async():
    """
    Build SDK clients inside a running loop so aiohttp is happy.
    NOTE: TransactionApi takes an ApiClient, not 'url='.
    """
    # SignerClient accepts url + keys
    signer = lighter.SignerClient(
        url=BASE_URL,
        private_key=API_PRIV,
        account_index=ACCOUNT_INDEX,
        api_key_index=API_KEY_INDEX,
    )
    # TransactionApi requires ApiClient(Configuration(host=...))
    cfg = lighter.Configuration(host=BASE_URL)
    api_client = lighter.ApiClient(configuration=cfg)
    tx_api = lighter.TransactionApi(api_client)
    return signer, tx_api

def get_clients():
    """
    Ensure a loop exists; create and cache SignerClient + TransactionApi once.
    """
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

    symbol = str(body.get("symbol", "BTC-USDC"))
    side   = str(body.get("side", "buy")).lower()
    qty    = float(str(body.get("qty", "0.0001")))

    # scale to base units (example: 1e8)
    base_amount = int(qty * 1_0000_0000)

    signer, tx_api = get_clients()

    # MARKET IOC
    signed_tx = signer.sign_create_order(
        market=symbol,
        side=side,
        base_amount=base_amount,
        price=0,  # market
        client_order_index=0,
        time_in_force="ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL",
        order_type="ORDER_TYPE_MARKET",
    )

    resp = tx_api.send_tx(signed_tx)
    print("Lighter send_tx response:", resp, flush=True)
    return jsonify({"ok": True, "lighter_response": resp})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print("URL MAP:", app.url_map, flush=True)
    app.run(host="0.0.0.0", port=port)
