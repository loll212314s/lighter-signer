import os, hmac, hashlib, base64, json
from flask import Flask, request, jsonify

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
PRIVATE_KEY   = os.environ.get("API_KEY_PRIVATE_KEY") or os.environ.get("LIGHTER_PRIVATE_KEY")
PUBLIC_KEY    = os.environ.get("API_KEY_PUBLIC_KEY", "")
ACCOUNT_INDEX = int(os.environ.get("ACCOUNT_INDEX", "0"))
API_KEY_INDEX = int(os.environ.get("API_KEY_INDEX", "0"))

def hmac_b64(message: str, key: str) -> str:
    mac = hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode("utf-8").rstrip("=")

@app.get("/")
def root():
    return jsonify({"status": "ok"})

@app.post("/sign")
def sign():
    if not PRIVATE_KEY:
        return jsonify({"ok": False, "error": "missing API_KEY_PRIVATE_KEY"}), 500
    raw = request.get_data(as_text=True) or ""
    if raw.strip() == "":
        raw = "{}"
    sig = hmac_b64(raw, PRIVATE_KEY)
    print("Sign request:", raw, "->", sig, flush=True)
    return jsonify({"ok": True, "message": raw, "signature": sig})

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return jsonify({"ok": True, "note": "send POST with JSON"}), 200

    if not PRIVATE_KEY:
        return jsonify({"ok": False, "error": "missing API_KEY_PRIVATE_KEY"}), 500

    data = request.get_json(force=True, silent=True) or {}

    # 1) simple TradingView password
    if WEBHOOK_SECRET and data.get("secret") != WEBHOOK_SECRET:
        print("bad secret:", data.get("secret"), flush=True)
        return jsonify({"ok": False, "error": "bad secret"}), 401

    # 2) inner trading payload (what we’ll sign for Lighter)
    # example from TradingView: {"secret":"...","symbol":"BTCUSDT","side":"buy","qty":"0.001"}
    payload = {k: v for k, v in data.items() if k != "secret"}
    # you can extend payload with leverage, reduceOnly, etc.

    # 3) sign the inner payload for Lighter
    message = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    signature = hmac_b64(message, PRIVATE_KEY)

    signed_packet = {
        "public_key": PUBLIC_KEY,     # desktop public key
        "account_index": ACCOUNT_INDEX,
        "api_key_index": API_KEY_INDEX,
        "message": message,           # string
        "signature": signature        # base64url HMAC-SHA256 of message
    }

    print("Verified TV alert:", payload, flush=True)
    print("SignedForLighter:", json.dumps(signed_packet), flush=True)

    # (next step we’ll POST signed_packet to Lighter’s order endpoint)
    return jsonify({"ok": True, "prepared_for_lighter": signed_packet}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print("URL MAP:", app.url_map, flush=True)
    app.run(host="0.0.0.0", port=port)
