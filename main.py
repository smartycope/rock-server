from flask import Flask, request, jsonify
import subprocess
import git
import os


SERVICE_NAME = "rock-server"  # Your systemd service name
repo = git.Repo("/home/rock/rock-server")
app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello, world!"

@app.route("/restart", methods=["POST"])
def restart_service():
    try:
        subprocess.run(["sudo", "systemctl", "restart", SERVICE_NAME], check=True)
        return jsonify({"status": "restarted"}), 200
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        origin = repo.remotes.origin
        origin.pull()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return restart_service()

if __name__ == "__main__":
    app.run()
