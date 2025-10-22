import os, hmac, hashlib, base64, json, urllib.request
from flask import Flask, request, jsonify

app = Flask(__name__)

WEBHOOK_SECRET   = os.environ.get("WEBHOOK_SECRET", "")
PRIVATE_KEY      = os.environ.get("API_KEY_PRIVATE_KEY") or os.environ.get("LIGHTER_PRIVATE_KEY")
PUBLIC_KEY       = os.environ.get("API_KEY_PUBLIC_KEY", "")
ACCOUNT_INDEX    = int(os.environ.get("ACCOUNT_INDEX", "0"))
API_KEY_INDEX    = int(os.environ.get("API_KEY_INDEX", "0"))
LIGHTER_ORDERS_URL = os.environ.get("LIGHTER_ORDERS_URL", "").strip()  # leave blank for dry-run

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

    # password for TradingView
    if WEBHOOK_SECRET and data.get("secret") != WEBHOOK_SECRET:
        print("bad secret:", data.get("secret"), flush=True)
        return jsonify({"ok": False, "error": "bad secret"}), 401

    # inner payload from TV (strip secret)
    payload = {k: v for k, v in data.items() if k != "secret"}

    # sign payload
    message   = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    signature = hmac_b64(message, PRIVATE_KEY)

    signed_packet = {
        "public_key": PUBLIC_KEY,
        "account_index": ACCOUNT_INDEX,
        "api_key_index": API_KEY_INDEX,
        "message": message,
        "signature": signature
    }

    print("Verified TV alert:", payload, flush=True)
    print("SignedForLighter:", json.dumps(signed_packet), flush=True)

    # optionally POST to Lighter if URL is set
    if LIGHTER_ORDERS_URL:
        try:
            req = urllib.request.Request(
                LIGHTER_ORDERS_URL,
                data=json.dumps(signed_packet).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", "ignore")
                print("LighterResp:", resp.status, body[:500], flush=True)
        except Exception as e:
            print("LighterErr:", repr(e), flush=True)

    return jsonify({"ok": True, "prepared_for_lighter": bool(LIGHTER_ORDERS_URL)}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print("URL MAP:", app.url_map, flush=True)
    app.run(host="0.0.0.0", port=port)
