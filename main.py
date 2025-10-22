import os, json, asyncio
from flask import Flask, request, jsonify
import lighter  # from requirements.txt (lighter-python)

app = Flask(__name__)

BASE_URL       = os.environ.get("BASE_URL", "https://mainnet.zklighter.elliot.ai")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
API_PRIV       = os.environ.get("API_KEY_PRIVATE_KEY") or os.environ.get("LIGHTER_PRIVATE_KEY")
ACCOUNT_INDEX  = int(os.environ.get("ACCOUNT_INDEX", "0"))
API_KEY_INDEX  = int(os.environ.get("API_KEY_INDEX", "0"))

# lazy-initialized SDK clients (so we can ensure an event loop exists)
_app_clients_key = "_lighter_clients"

def get_clients():
    """
    Ensure an asyncio event loop exists, then create and cache SignerClient + TransactionApi.
    """
    # make sure there is a running loop for aiohttp used by the SDK
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    clients = app.config.get(_app_clients_key)
    if clients is None:
        signer = lighter.SignerClient(
            url=BASE_URL,
            private_key=API_PRIV,
            account_index=ACCOUNT_INDEX,
            api_key_index=API_KEY_INDEX,
        )
        tx_api = lighter.TransactionApi(url=BASE_URL)
        clients = (signer, tx_api)
        app.config[_app_clients_key] = clients
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
