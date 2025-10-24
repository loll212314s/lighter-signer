# main.py — Lighter webhook (final v5: strict signature + awaits)
import os, json, asyncio, logging
from flask import Flask, request, jsonify
import lighter

logging.getLogger("werkzeug").setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

app = Flask(__name__)

BASE_URL = os.environ.get("BASE_URL", "https://mainnet.zklighter.elliot.ai").rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
API_PRIV = os.environ.get("API_KEY_PRIVATE_KEY") or os.environ.get("LIGHTER_PRIVATE_KEY")
ACCOUNT_INDEX = os.environ.get("ACCOUNT_INDEX")
API_KEY_INDEX = os.environ.get("API_KEY_INDEX")
MARKET_INDEX = os.environ.get("MARKET_INDEX")

_CLIENTS_KEY = "_lighter_clients"

def _need_envs():
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

def _await(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    if loop.is_running():
        return asyncio.run(coro)
    return loop.run_until_complete(coro)

def _get_clients():
    c = app.config.get(_CLIENTS_KEY)
    if c: return c
    c = _await(_make_clients_async())
    app.config[_CLIENTS_KEY] = c
    return c

@app.get("/")
def root():
    return jsonify({"status": "ok", "version": "final-v5"})

@app.post("/webhook")
def webhook():
    miss = _need_envs()
    if miss:
        return jsonify({"ok": False, "error": "missing env", "need": miss}), 400

    data = request.get_json(force=True, silent=True) or {}
    if WEBHOOK_SECRET and data.get("secret") != WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "bad secret"}), 401

    side = str(data.get("side", "buy")).lower()
    is_ask = side in ("sell","short")  # sell = ask

    try:
        qty = float(str(data.get("qty", "0.0001")))
    except Exception:
        return jsonify({"ok": False, "error": "bad qty"}), 400
    if qty <= 0:
        return jsonify({"ok": False, "error": "qty must be > 0"}), 400

    try:
        market_index = int(data.get("market_index", MARKET_INDEX))
    except Exception as e:
        return jsonify({"ok": False, "error": f"bad market_index: {e}"}), 400

    base_amount = int(qty * 1_0000_0000)  # adjust scale if needed

    try:
        signer, tx_api = _get_clients()
        # STRICT order your SDK expects: (market_index, base_amount, is_ask, client_order_index)
        tx = signer.create_market_order(int(market_index), int(base_amount), bool(is_ask), 0)
        if asyncio.iscoroutine(tx):
            tx = _await(tx)

        resp = tx_api.send_tx(tx)
        if asyncio.iscoroutine(resp):
            resp = _await(resp)

        return jsonify({"ok": True, "lighter_response": resp}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": "send_tx failed", "detail": str(e)}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
