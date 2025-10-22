import os
from flask import Flask, request, jsonify, abort

app = Flask(__name__)

SECRET = os.environ.get("WEBHOOK_SECRET", "")

@app.get("/")
def root():
    return jsonify({"status": "ok"})

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return jsonify({"ok": True, "note": "send POST with JSON"}), 200

    data = request.get_json(force=True, silent=True) or {}

    # simple auth: require matching secret in body
    if SECRET:
        if data.get("secret") != SECRET:
            print("bad secret:", data.get("secret"), flush=True)
            return jsonify({"ok": False, "error": "bad secret"}), 401

    print("Received:", data, flush=True)
    return jsonify({"ok": True, "echo": data}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print("URL MAP:", app.url_map, flush=True)
    app.run(host="0.0.0.0", port=port)
