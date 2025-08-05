from flask import Flask, redirect, request, jsonify, render_template, url_for
import subprocess
import git
import logging
import psutil
import os
import time
from pathlib import Path
import threading
from flask import has_request_context, request
from collections import deque

# If we're running on the server, we're not debugging
DEBUG = os.uname().nodename != "rockpi-4b"
# This *doesn't* work, because we run the process as root
# DEBUG = os.getlogin() != "rock"
SERVICE_NAME = "rock-server"

app = Flask(__name__)
# Set the logger to debug level because we're filtering later
app.logger.setLevel(logging.DEBUG)
log = app.logger

class InMemoryHandler(logging.Handler):
    """ Custom in-memory log handler with fixed size """
    def __init__(self, formatter: logging.Formatter, capacity: int = 1000):
        super().__init__()
        self.records: deque[logging.LogRecord] = deque(maxlen=capacity)  # Keep last N records
        self.setFormatter(formatter)
        self.setLevel(logging.DEBUG)

    def emit(self, record: logging.LogRecord):
        self.records.append(record)

    def get_logs(self, level: str) -> list[str]:
        threshold = logging._nameToLevel[level]
        return [
            self.format(r)
            for r in self.records
            if r.levelno >= threshold
        ]

memory_handler = InMemoryHandler(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
app.logger.addHandler(memory_handler)


if not DEBUG:
    repo = git.Repo("/home/rock/rock-server")
    PYTHON_BINARY = "/home/rock/rock-server/bin/python"
else:
    repo = git.Repo(".")
    PYTHON_BINARY = "python"


@app.route("/")
def index():
    log.info("Hello, world!")
    app.logger.debug("This is a debug log.")
    app.logger.info("This is an info log.")
    app.logger.warning("This is a warning log.")
    return "Hello, world!"

@app.errorhandler(404)
def not_found(error):
    """ Return a 404 error page """
    return redirect(url_for('static', filename='error.html'))

def restart_service():
    time.sleep(0.1)
    log.info("Service restarting")
    if not DEBUG:
        subprocess.run(["sudo", "systemctl", "restart", SERVICE_NAME])
    else:
        # simulate a SIGTERM
        exit(15)

@app.route("/restart", methods=["POST"])
def restart():
    """ Restart the server """
    try:
        # Start a new thread, have it restart the service after a short delay
        threading.Thread(target=restart_service).start()
        return {"status": "restarted"}, 200
    except subprocess.CalledProcessError as e:
        log.error("Failed to restart service: %s", e)
        return {"error": str(e)}, 500

@app.route("/github-webhook", methods=["POST"])
def github_webhook():
    """ Triggered by the github repo. Pulls the latest changes and restarts the server """
    log.info("Github change detected")
    try:
        log.info("Pulling from remote...")
        origin = repo.remotes.origin
        origin.pull()
        repo.submodule_update(init=True, recursive=True)
        log.info("Pull successful")
        threading.Thread(target=restart_service).start()
    except subprocess.CalledProcessError as e:
        log.error("Failed to restart service: %s", e)
        return {"error": str(e)}, 500
    except Exception as e:
        log.error("Failed to pull from remote: %s", e)
        return {"error": str(e)}, 500
    return {"status": "restarted"}, 200

@app.route("/info")
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

@app.route("/install/<package>", methods=["POST"])
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

@app.route("/docs")
def docs():
    """ Return the documentation """
    return redirect(url_for("static", filename="docs/index.html"))

@app.route('/logs/<level>')
def get_logs(level):
    level = level.upper()
    if level not in logging._nameToLevel:
        return f'Invalid level: {level}', 400

    return '<br/>'.join(memory_handler.get_logs(level))

@app.before_request
def log_request_info():
    """ Log all requests """
    log.debug("Request: %s %s", request.method, request.url)

if __name__ == "__main__":
    log.info("Server started via main")
    # Gunicorn will handles the server port and IP
    app.run()
