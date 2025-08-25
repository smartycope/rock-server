from flask import redirect, request, render_template, send_file, url_for, current_app, Blueprint
import subprocess
import git
import logging
import psutil
import os
import time
from pathlib import Path
import threading

bp = Blueprint("system_endpoints", __name__)

log = current_app.logger

SERVICE_NAME = "rock-server"
if not current_app.DEBUG:
    repo = git.Repo("/home/rock/rock-server")
    PYTHON_BINARY = "/home/rock/rock-server/bin/python"
else:
    repo = git.Repo(".")
    PYTHON_BINARY = "python"


@bp.route("/")
def index():
    log.info("Hello, world!")
    log.debug("This is a debug log.")
    log.info("This is an info log.")
    log.warning("This is a warning log.")
    log.error("This is an error log.")
    return "Hello, world!"

@bp.errorhandler(404)
def not_found(error):
    """ Return a 404 error page """
    return render_template('error.html', error=error), 404

def restart_service():
    time.sleep(0.1)
    log.info("Service restarting")
    if not current_app.DEBUG:
        # We don't need to check here, since this process will immediately be terminated as soon as it runs
        subprocess.run(["sudo", "systemctl", "restart", SERVICE_NAME])
    else:
        # simulate a SIGTERM
        exit(15)

@bp.route("/restart/", methods=["POST"])
def restart():
    """ Restart the server """
    try:
        # Start a new thread, have it restart the service after a short delay
        threading.Thread(target=restart_service).start()
        return {"status": "restarted"}, 200
    except subprocess.CalledProcessError as e:
        log.error("Failed to restart service: %s", e)
        return {"error": str(e)}, 500

@bp.route("/github-webhook/", methods=["POST"])
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

@bp.route("/info/")
def info():
    """ Return information about the server """
    proc = psutil.Process(os.getpid())
    start_time = proc.create_time()
    uptime_seconds = time.time() - start_time
    return {
            "status": "ok",
            "server_started": time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(start_time)),
            "uptime_seconds": uptime_seconds,
            "uptime_human": time.strftime("%H:%M:%S", time.localtime(uptime_seconds)),
            "current_packages": subprocess.check_output([PYTHON_BINARY, "-m", "pip", "freeze"]).decode("utf-8").split("\n"),
            "storage_available": str(round(psutil.disk_usage("/").free / 1024 / 1024 / 1024, 2)) + " GB",
            "storage_total": str(round(psutil.disk_usage("/").total / 1024 / 1024 / 1024, 2)) + " GB",
            "storage_percent": psutil.disk_usage("/").percent,
            "pi_uptime_seconds": time.time() - psutil.boot_time(),
            "pi_uptime_human": time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(time.time() - psutil.boot_time())),
            "last_commit_msg": repo.head.commit.message,
            "last_commit_time": time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(repo.head.commit.authored_date)),
            "last_commit_age": time.strftime("%H:%M:%S", time.localtime(time.time() - repo.head.commit.authored_date)),
        }, 200

@bp.route("/install/<package>/", methods=["POST"])
def install_package(package):
    """ Install a package using pip """
    try:
        log.info("Installing %s...", package)
        subprocess.run([PYTHON_BINARY, "-m", "pip", "install", package], check=True)
        log.info("%s installed", package)
    except Exception as e:
        log.error("Failed to install %s: %s", package, e)
        return {"error": str(e)}, 500
    return {"status": "ok"}, 200

# TODO: move this into it's own project
@bp.route("/sex-dice/")
def sex_dice():
    """ Return the sex dice page """
    return send_file('static/sex-dice.html')


@bp.route('/coffee/')
def coffee():
    """ Return a 418 I'm a teapot response """
    return 'Error 418: I can\'t brew coffee, I\'m a teapot', 418


@bp.route("/docs/")
def docs():
    """ Return the documentation """
    return redirect(url_for("static", filename="docs/index.html"))

# TODO: this should work, but it doesn't
@bp.route('/logs/')
def logs():
    """ The default log level is INFO """
    return redirect(url_for(".get_logs", level='info'))

@bp.route('/logs/<level>/')
def get_logs(level):
    level = level.upper()
    if level not in logging._nameToLevel:
        return f'Invalid level: {level}', 400

    threshold = logging._nameToLevel[level]
    lines = []

    try:
        with open(current_app.LOG_FILE, 'r') as f:
            for line in f:
                try:
                    levelname = line.split(' - ')[1]
                    if logging._nameToLevel.get(levelname, 100) >= threshold:
                        lines.append(line.strip())
                except Exception:
                    continue  # skip malformed lines
    except FileNotFoundError:
        lines.append("Log file not found.")

    return render_template('logs_template.html', logs=reversed(lines))

@bp.before_request
def log_request_info():
    """ Log all requests """
    log.debug("Request: %s %s", request.method, request.url)
