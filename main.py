import os, hmac, hashlib, base64, json
from flask import Flask, request, jsonify, abort

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
PRIVATE_KEY = os.environ.get("API_KEY_PRIVATE_KEY") or os.environ.get("LIGHTER_PRIVATE_KEY")

@app.get("/")
def root():
    return jsonify({"status": "ok"})

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return jsonify({"ok": True, "note": "send POST with JSON"}), 200

    data = request.get_json(force=True, silent=True) or {}

    # simple auth for TradingView alerts
    if WEBHOOK_SECRET and data.get("secret") != WEBHOOK_SECRET:
        print("bad secret:", data.get("secret"), flush=True)
        return jsonify({"ok": False, "error": "bad secret"}), 401

    print("Received:", data, flush=True)
    return jsonify({"ok": True, "echo": data}), 200

@app.post("/sign")
def sign():
    """
    Signs the raw JSON body using HMAC-SHA256 with your PRIVATE_KEY.
    Returns base64 signature and the exact message that was signed.
    """
    if not PRIVATE_KEY:
        return jsonify({"ok": False, "error": "missing API_KEY_PRIVATE_KEY"}), 500

    # Read raw body exactly as sent
    raw = request.get_data(as_text=True) or ""
    # Normalize empty to "{}" to avoid confusion
    if raw.strip() == "":
        raw = "{}"

    # HMAC-SHA256
    mac = hmac.new(PRIVATE_KEY.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(mac).decode("utf-8").rstrip("=")

    print("Sign request:", raw, " -> sig:", sig_b64, flush=True)
    return jsonify({"ok": True, "message": raw, "signature": sig_b64})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print("URL MAP:", app.url_map, flush=True)
    app.run(host="0.0.0.0", port=port)
