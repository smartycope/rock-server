from flask import Flask, request, jsonify
import subprocess
import git
import os
import logging


SERVICE_NAME = "rock-server"
repo = git.Repo("/home/rock/rock-server")
app = Flask(__name__)

@app.route("/")
def hello():
    logging.info("Hello, world!")
    return "Hello, world!"

@app.route("/restart", methods=["POST"])
def restart_service():
    # I've disabled error handling, because restarting this process will naturally
    # cause a system exit (15) error. This works every time I try it, so I'm
    # calling it good
    # try:
    logging.info("Restarting service...")
    subprocess.run(["sudo", "systemctl", "restart", SERVICE_NAME], check=True)
    logging.info("Service restarted")
    return jsonify({"status": "restarted"}), 200
    # except subprocess.CalledProcessError as e:
    #     return jsonify({"error": str(e)}), 500

@app.route("/github-webhook", methods=["POST"])
def github_webhook():
    logging.info("Github change detected")
    try:
        logging.info("Pulling from remote...")
        origin = repo.remotes.origin
        origin.pull()
        logging.info("Pull successful")
    except Exception as e:
        logging.error("Failed to pull from remote: %s", e)
        return jsonify({"error": str(e)}), 500
    return restart_service()

if __name__ == "__main__":
    logging.info("Server started")
    app.run()
