import os, hmac, hashlib, base64, json
from flask import Flask, request, jsonify

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
PRIVATE_KEY = os.environ.get("API_KEY_PRIVATE_KEY") or os.environ.get("LIGHTER_PRIVATE_KEY")

def hmac_b64(message: str, key: str) -> str:
    mac = hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode("utf-8").rstrip("=")

@app.get("/")
def root():
    return jsonify({"status": "ok"})

@app.post("/sign")
def sign():
    """Sign the RAW body you send (e.g. {"symbol":"BTCUSDT","side":"buy","qty":"0.001"})."""
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

    data = request.get_json(force=True, silent=True) or {}

    # 1) simple password check (TradingView can't set headers)
    if WEBHOOK_SECRET and data.get("secret") != WEBHOOK_SECRET:
        print("bad secret:", data.get("secret"), flush=True)
        return jsonify({"ok": False, "error": "bad secret"}), 401

    # 2) SIGNATURE CHECK
    # Expect structure:
    # {
    #   "secret":"<WEBHOOK_SECRET>",
    #   "message":"{\"symbol\":\"BTCUSDT\",\"side\":\"buy\",\"qty\":\"0.001\"}",
    #   "signature":"<base64urlsafe HMAC-SHA256 of message using PRIVATE_KEY>"
    # }
    if not PRIVATE_KEY:
        return jsonify({"ok": False, "error": "missing API_KEY_PRIVATE_KEY"}), 500

    message = data.get("message")
    signature = data.get("signature")
    if not isinstance(message, str) or not isinstance(signature, str):
        return jsonify({"ok": False, "error": "missing message or signature"}), 400

    expected = hmac_b64(message, PRIVATE_KEY)
    if signature != expected:
        print("bad sig:", signature, "expected:", expected, flush=True)
        return jsonify({"ok": False, "error": "bad signature"}), 401

    # parse the inner payload to act on it
    try:
        inner = json.loads(message)
    except Exception as e:
        return jsonify({"ok": False, "error": "invalid inner message", "detail": str(e)}), 400

    print("Verified:", inner, flush=True)
    return jsonify({"ok": True, "verified": True, "payload": inner}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print("URL MAP:", app.url_map, flush=True)
    app.run(host="0.0.0.0", port=port)
