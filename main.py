import os, json
from flask import Flask, request, jsonify
import lighter  # from requirements.txt (lighter-python)

app = Flask(__name__)

BASE_URL       = os.environ.get("BASE_URL", "https://mainnet.zklighter.elliot.ai")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
API_PRIV       = os.environ.get("API_KEY_PRIVATE_KEY") or os.environ.get("LIGHTER_PRIVATE_KEY")
ACCOUNT_INDEX  = int(os.environ.get("ACCOUNT_INDEX", "0"))
API_KEY_INDEX  = int(os.environ.get("API_KEY_INDEX", "0"))

signer = lighter.SignerClient(
    url=BASE_URL,
    private_key=API_PRIV,
    account_index=ACCOUNT_INDEX,
    api_key_index=API_KEY_INDEX,
)
tx_api = lighter.TransactionApi(url=BASE_URL)

@app.get("/")
def root():
    return jsonify({"status": "ok"})

@app.post("/webhook")
def webhook():
    body = request.get_json(force=True, silent=True) or {}
    if WEBHOOK_SECRET and body.get("secret") != WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "bad secret"}), 401

    # Example payload from TradingView:
    # {"secret":"...","symbol":"BTC-USDC","side":"buy","qty":"0.0001"}
    symbol = str(body.get("symbol", "BTC-USDC"))
    side   = str(body.get("side", "buy")).lower()
    qty    = float(str(body.get("qty", "0.0001")))

    # Scale to base units (adjust if your market uses different decimals)
    base_amount = int(qty * 1_0000_0000)  # 1e8

    # MARKET IOC (safe tiny test)
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
