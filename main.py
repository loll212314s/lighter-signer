import os
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.get("/")
def root():
    return jsonify({"status": "ok"})

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return jsonify({"ok": True, "note": "send POST with JSON"}), 200

    data = request.get_json(force=True, silent=True) or {}
    print("Received:", data, flush=True)  # shows in Render Logs
    return jsonify({"ok": True, "echo": data}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))  # use Render's PORT
    app.run(host="0.0.0.0", port=port)
