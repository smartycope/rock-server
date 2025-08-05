from flask import Flask, redirect, request, jsonify, render_template, url_for
import subprocess
import git
import logging
import io
import psutil
import os
import time
from pathlib import Path


# If we're running on the server, we're not debugging
DEBUG = os.uname().nodename != "rockpi-4b"
# This *doesn't* work, because we run the process as root
# DEBUG = os.getlogin() != "rock"
SERVICE_NAME = "rock-server"

# Custom logging, since it's not super accessible using gunicorn
log_stream = io.StringIO('Server started')
handler = logging.StreamHandler(log_stream)
log = logging.getLogger("my_logger")
log.setLevel(logging.INFO)
log.addHandler(handler)
# Format logs as HTML
formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
handler.setFormatter(formatter)

if not DEBUG:
    repo = git.Repo("/home/rock/rock-server")
    PYTHON_BINARY = "/home/rock/rock-server/bin/python"
else:
    repo = git.Repo(".")
    PYTHON_BINARY = "python"

app = Flask(__name__)

@app.route("/")
def index():
    log.info("Hello, world!")
    return "Hello, world!"

@app.route("/restart/", methods=["POST"])
def restart_service():
    """ Restart the server """
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

@app.route("/github-webhook/", methods=["POST"])
def github_webhook():
    """ Triggered by the github repo. Pulls the latest changes and restarts the server """
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

@app.route("/logs/")
def logs():
    """ Return the server logs """
    return render_template("logs_template.html", logs=log_stream.getvalue()), 200

@app.route("/info/")
def info():
    """ Return information about the server """
    proc = psutil.Process(os.getpid())
    start_time = proc.create_time()
    uptime_seconds = time.time() - start_time
    return jsonify(
        {
            "status": "ok",
            "server_started": time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(start_time)),
            "uptime_seconds": uptime_seconds,
            "uptime_human": time.strftime("%H:%M:%S", time.localtime(uptime_seconds)),
            "current_packages": subprocess.check_output([PYTHON_BINARY, "-m", "pip", "freeze"]).decode("utf-8").split("\n"),
            # "logs": log_stream.getvalue()
        }
    ), 200

@app.route("/install/<package>/", methods=["POST"])
def install_package(package):
    """ Install a package using pip """
    try:
        log.info("Installing %s...", package)
        subprocess.run([PYTHON_BINARY, "-m", "pip", "install", package], check=True)
        log.info("%s installed", package)
    except Exception as e:
        log.error("Failed to install %s: %s", package, e)
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "ok"}), 200

# There's probably a better, more flasky way to do this
@app.route("/docs/")
def docs():
    """ Return the documentation """
    return redirect(url_for("static", filename="docs/index.html"))

# Log all requests
@app.before_request
def log_request_info():
    log.info("Request: %s %s", request.method, request.url)

if __name__ == "__main__":
    log.info("Server started via main")
    # Gunicorn will handles the server port and IP
    app.run()
