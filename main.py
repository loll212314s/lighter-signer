
# main.py — Lighter webhook (final, uses SDK helper to avoid enum errors)
import os, json, asyncio, logging
from flask import Flask, request, jsonify
import lighter  # from requirements.txt (lighter-python)

# calm noisy logs
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.INFO)

app = Flask(__name__)

# --- REQUIRED ENVs ---
BASE_URL = os.environ.get("BASE_URL", "https://mainnet.zklighter.elliot.ai").rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
API_PRIV = os.environ.get("API_KEY_PRIVATE_KEY") or os.environ.get("LIGHTER_PRIVATE_KEY")
ACCOUNT_INDEX = os.environ.get("ACCOUNT_INDEX")
API_KEY_INDEX = os.environ.get("API_KEY_INDEX")
MARKET_INDEX = os.environ.get("MARKET_INDEX")  # default market index (e.g., 1 for BTC-USDC)

_CLIENTS_KEY = "_lighter_clients"

def _missing_envs():
    miss = []
    if not API_PRIV: miss.append("API_KEY_PRIVATE_KEY")
    if ACCOUNT_INDEX is None: miss.append("ACCOUNT_INDEX")
    if API_KEY_INDEX is None: miss.append("API_KEY_INDEX")
    if MARKET_INDEX is None: miss.append("MARKET_INDEX")
    return miss

async def _make_clients_async():
    signer = lighter.SignerClient(
        url=BASE_URL,
        private_key=API_PRIV,
        account_index=int(ACCOUNT_INDEX),
        api_key_index=int(API_KEY_INDEX),
    )
    cfg = lighter.Configuration(host=BASE_URL)
    api_client = lighter.ApiClient(configuration=cfg)
    tx_api = lighter.TransactionApi(api_client)
    return signer, tx_api

def _get_clients():
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
    # Check envs first
    miss = _missing_envs()
    if miss:
        return jsonify({"ok": False, "error": "missing env", "need": miss}), 400

    body = request.get_json(force=True, silent=True) or {}
    if WEBHOOK_SECRET and body.get("secret") != WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "bad secret"}), 401

    # Inputs
    side = str(body.get("side", "buy")).lower()  # "buy" / "sell"
    try:
        qty = float(str(body.get("qty", "0.0001")))
    except Exception:
        return jsonify({"ok": False, "error": "bad qty"}), 400
    if qty <= 0:
        return jsonify({"ok": False, "error": "qty must be > 0"}), 400

    # Market index can be overridden by body; else use env
    try:
        market_index = int(body.get("market_index", MARKET_INDEX))
    except Exception as e:
        return jsonify({"ok": False, "error": f"bad market_index: {e}"}), 400

    # Scale to base units (example: 1e8)
    base_amount = int(qty * 1_0000_0000)

    try:
        signer, tx_api = _get_clients()

        # Use SDK helper to avoid enum integer issues
        signed_tx = signer.create_market_order(
            market_index=market_index,
            side=side,  # "buy" or "sell"
            base_amount=base_amount,
            client_order_index=0,
        )

        resp = tx_api.send_tx(signed_tx)
        print("Lighter send_tx response:", resp, flush=True)
        return jsonify({"ok": True, "lighter_response": resp}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": "send_tx failed", "detail": str(e)}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print("URL MAP:", app.url_map, flush=True)
    app.run(host="0.0.0.0", port=port)
