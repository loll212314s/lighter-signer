# main.py — Lighter webhook (create_market_order signature-agnostic, dual-sig-v2)
import os, json, asyncio, logging
from flask import Flask, request, jsonify
import lighter  # pip install lighter-python

logging.getLogger("werkzeug").setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

app = Flask(__name__)

BASE_URL = os.environ.get("BASE_URL", "https://mainnet.zklighter.elliot.ai").rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
API_PRIV = os.environ.get("API_KEY_PRIVATE_KEY") or os.environ.get("LIGHTER_PRIVATE_KEY")
ACCOUNT_INDEX = os.environ.get("ACCOUNT_INDEX")
API_KEY_INDEX = os.environ.get("API_KEY_INDEX")
MARKET_INDEX = os.environ.get("MARKET_INDEX")  # default

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

def _get_clients():
    c = app.config.get(_CLIENTS_KEY)
    if c: return c
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    if not loop.is_running():
        c = loop.run_until_complete(_make_clients_async())
    else:
        fut = asyncio.run_coroutine_threadsafe(_make_clients_async(), loop)
        c = fut.result()
    app.config[_CLIENTS_KEY] = c
    return c

@app.get("/")
def root():
    return jsonify({"status": "ok", "version": "dual-sig-v2"})

@app.post("/webhook")
def webhook():
    miss = _need_envs()
    if miss:
        return jsonify({"ok": False, "error": "missing env", "need": miss}), 400

    data = request.get_json(force=True, silent=True) or {}
    if WEBHOOK_SECRET and data.get("secret") != WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "bad secret"}), 401

    # side -> is_ask (sell/short = ask=true, buy/long = ask=false)
    side_str = str(data.get("side", "buy")).lower()
    is_ask = side_str in ("sell", "short")

    # qty
    try:
        qty = float(str(data.get("qty", "0.0001")))
    except Exception:
        return jsonify({"ok": False, "error": "bad qty"}), 400
    if qty <= 0:
        return jsonify({"ok": False, "error": "qty must be > 0"}), 400

    # market index
    try:
        market_index = int(data.get("market_index", MARKET_INDEX))
    except Exception as e:
        return jsonify({"ok": False, "error": f"bad market_index: {e}"}), 400

    # convert to base units (example scale 1e8)
    base_amount = int(qty * 1_0000_0000)

    try:
        signer, tx_api = _get_clients()

        # Try multiple known SDK signatures. We stop at the first that works.
        mi = int(market_index); ba = int(base_amount); ia = bool(is_ask)
        attempts = [
            ( (mi, ba, ia, 0), {} ),                                # A: (mi, base_amount, is_ask, coi)
            ( (mi, ia, ba, 0), {} ),                                # B: (mi, is_ask, base_amount, coi)
            ( (), {"market_index": mi, "base_amount": ba, "is_ask": ia, "client_order_index": 0} ),   # C kwargs
            ( (), {"market_index": mi, "is_ask": ia, "base_amount": ba, "client_order_index": 0} ),   # D kwargs alt
            ( (mi, 0, ba, ia, 0), {} ),                             # E: (mi, price=0, base_amount, is_ask, coi)
            ( (mi, 0, ia, ba, 0), {} ),                             # F: (mi, price=0, is_ask, base_amount, coi)
        ]

        last_err = None
        signed_tx = None
        for args, kwargs in attempts:
            try:
                signed_tx = signer.create_market_order(*args, **kwargs)
                print("create_market_order pattern OK:", (args or kwargs), flush=True)
                break
            except TypeError as e:
                last_err = str(e)
                continue

        if not signed_tx:
            return jsonify({
                "ok": False,
                "error": "send_tx failed",
                "detail": f"no matching create_market_order signature; last: {last_err}"
            }), 400

        resp = tx_api.send_tx(signed_tx)
        print("Lighter send_tx response:", resp, flush=True)
        return jsonify({"ok": True, "lighter_response": resp}), 200

    except Exception as e:
        return jsonify({"ok": False, "error": "send_tx failed", "detail": str(e)}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
