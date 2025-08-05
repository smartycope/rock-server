from flask import Flask, request, jsonify
import subprocess
import git
import os
import logging
import io

# Custom logging, since it's not super accessible using gunicorn
log_stream = io.StringIO()
handler = logging.StreamHandler(log_stream)
log = logging.getLogger("my_logger")
log.setLevel(logging.INFO)
log.addHandler(handler)

SERVICE_NAME = "rock-server"
repo = git.Repo("/home/rock/rock-server")
app = Flask(__name__)

@app.route("/")
def hello():
    log.info("Hello, world!")
    return "Hello, world!"

@app.route("/restart", methods=["POST"])
def restart_service():
    # I've disabled error handling, because restarting this process will naturally
    # cause a SIGTERM (15) error. This works every time I try it, so I'm
    # calling it good
    # try:
    log.info("Restarting service...")
    subprocess.run(["sudo", "systemctl", "restart", SERVICE_NAME], check=True)
    log.info("Service restarted")
    return jsonify({"status": "restarted"}), 200
    # except subprocess.CalledProcessError as e:
    #     return jsonify({"error": str(e)}), 500

@app.route("/github-webhook", methods=["POST"])
def github_webhook():
    log.info("Github change detected")
    try:
        log.info("Pulling from remote...")
        origin = repo.remotes.origin
        origin.pull()
        log.info("Pull successful")
    except Exception as e:
        log.error("Failed to pull from remote: %s", e)
        return jsonify({"error": str(e)}), 500
    return restart_service()

@app.route("/logs")
def logs():
    return log_stream.getvalue()

if __name__ == "__main__":
    log.info("Server started")
    # Gunicorn will handles the server port and IP
    app.run()
