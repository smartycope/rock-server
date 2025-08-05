from flask import Flask, request, jsonify
import subprocess
import git
import logging
import io
import psutil
import os
import time

# Custom logging, since it's not super accessible using gunicorn
log_stream = io.StringIO('Server started')
handler = logging.StreamHandler(log_stream)
log = logging.getLogger("my_logger")
log.setLevel(logging.INFO)
log.addHandler(handler)

SERVICE_NAME = "rock-server"
repo = git.Repo("/home/rock/rock-server")
python_binary = "/home/rock/rock-server/bin/python"
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

@app.route("/info")
def info():
    proc = psutil.Process(os.getpid())
    start_time = proc.create_time()
    uptime_seconds = time.time() - start_time
    return jsonify(
        {
            "status": "ok",
            "server_started": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time)),
            "uptime": uptime_seconds,
            "uptime_human": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(uptime_seconds)),
            "current_packages": subprocess.check_output([python_binary, "-m", "pip", "freeze"]).decode("utf-8").split("\n"),
            "logs": log_stream.getvalue()
        }
    ), 200

@app.route("/install/<package>", methods=["POST"])
def install_package(package):
    """ Install a package using pip based on the package name """
    try:
        log.info("Installing %s...", package)
        subprocess.run([python_binary, "-m", "pip", "install", package], check=True)
        log.info("%s installed", package)
    except Exception as e:
        log.error("Failed to install %s: %s", package, e)
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "ok"}), 200

# Log all requests
@app.before_request
def log_request_info():
    log.info("Request: %s %s", request.method, request.url)

if __name__ == "__main__":
    log.info("Server started via main")
    # Gunicorn will handles the server port and IP
    app.run()
