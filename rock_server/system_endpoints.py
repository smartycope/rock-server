from flask import redirect, send_file, url_for, current_app, Blueprint
import subprocess
import git
import logging
import requests
import psutil
import os
import time
import datetime as dt
from pathlib import Path
import threading
from time import sleep
from .utils import format_logs, pretty_timedelta, format_line, generate_log_endpoints

bp = Blueprint("system_endpoints", __name__)

log = current_app.logger

SERVICE_NAME = "rock-server"
REMINDER_RUNNER_SERVICE_NAME = "reminders-runner"
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

def restart_service():
    """ Restart the service """
    sleep(0.1)
    log.info("Service restarting")
    # We don't have access to current_app in a seperate thread.
    # if not current_app.DEBUG:
    subprocess.run(["sudo", "systemctl", "restart", REMINDER_RUNNER_SERVICE_NAME])
    subprocess.run(["sudo", "systemctl", "restart", SERVICE_NAME])
    # simulate a SIGTERM if that didn't already
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

    irregular_reminders_info = {}
    try:
        irregular_reminders_info['status'] = requests.get("http://localhost:5050/", timeout=5).json()
    except Exception as e:
        irregular_reminders_info['status'] = 'Not running'
    else:
        try:
            irregular_reminders_info['process_info'] = requests.get("http://localhost:5050/scheduler", timeout=5).json()
        except Exception as e:
            irregular_reminders_info['process_info'] = f'Failed to get process info: {str(e)}'
        try:
            irregular_reminders_info['currently_running_jobs'] = requests.get("http://localhost:5050/scheduler/jobs", timeout=5).json()
        except Exception as e:
            irregular_reminders_info['currently_running_jobs'] = f'Failed to get jobs: {str(e)}'

    return {
            "status": "ok",
            "server_started": time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(start_time)),
            "uptime_seconds": uptime_seconds,
            "uptime_human": time.strftime("%H:%M:%S", time.localtime(uptime_seconds)),
            "current_packages": subprocess.check_output([PYTHON_BINARY, "-m", "pip", "freeze"]).decode("utf-8").split("\n") if not current_app.DEBUG else [],
            "storage_available": str(round(psutil.disk_usage("/").free / 1024 / 1024 / 1024, 2)) + " GB",
            "storage_total": str(round(psutil.disk_usage("/").total / 1024 / 1024 / 1024, 2)) + " GB",
            "storage_percent": psutil.disk_usage("/").percent,
            "pi_uptime_seconds": time.time() - psutil.boot_time(),
            "pi_uptime_human": time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(time.time() - psutil.boot_time())),
            "last_commit_msg": repo.head.commit.message,
            "last_commit_time": time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(repo.head.commit.authored_date)),
            "last_commit_age": time.strftime("%H:%M:%S", time.localtime(time.time() - repo.head.commit.authored_date)),
            "irregular_reminders": irregular_reminders_info,
        }, 200

@bp.route("/install/<package>", methods=["POST"])
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






# LOGS
generate_log_endpoints(bp, current_app.LOG_FILE, False)
generate_log_endpoints(bp, "system.log", True, postfix="/system")

# @bp.get('/logs/')
# def logs():
#     """ The default log level is INFO """
#     return redirect(url_for(".get_logs", level='info'))

# # System logs
# @bp.post('/logs/system/')
# def add_system_spacer():
#     with open("system.log", 'a') as f:
#         f.write("<hr/>\n")
#     return "Spacer added", 200

# @bp.delete('/logs/system/')
# def delete_system_logs():
#     with open("system.log", 'w') as f:
#         f.write("")
#     return "System logs cleared", 200

# @bp.get("/logs/system/stream")
# def stream_system_logs():
#     def generate():
#         with open("system.log", 'r') as f:
#             f.seek(0, 2)  # move to end of file
#             while True:
#                 line = f.readline()
#                 if line:
#                     yield f"data: {format_line(line)}\n\n"
#                 else:
#                     sleep(0.25)  # don’t busy loop
#     return Response(stream_with_context(generate()), mimetype="text/event-stream")

# @bp.get('/logs/system/<level>/')
# def get_system_logs(level):
#     level = level.upper()
#     if level not in logging._nameToLevel:
#         return f'Invalid level: {level}', 400
#     try:
#         with open("system.log", 'r') as f:
#             lines = format_logs(f.readlines(), logging._nameToLevel[level])
#     except FileNotFoundError:
#         lines = ["Log file not found."]
#     return render_template('logs_template.html',
#         logs=lines, clear_endpoint=url_for(".delete_system_logs"),
#         add_spacer_endpoint=url_for(".add_system_spacer"),
#         stream_endpoint=url_for(".stream_system_logs")
#     )
