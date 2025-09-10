from flask import redirect, request, render_template, send_file, url_for, current_app, Blueprint
import traceback
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

def restart_service():
    """ Restart the service """
    time.sleep(0.1)
    log.info("Service restarting")
    # We don't have access to current_app in a seperate thread.
    # if not current_app.DEBUG:
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

# TODO: this should work, but it doesn't
@bp.get('/logs/')
def logs():
    """ The default log level is INFO """
    return redirect(url_for(".get_logs", level='info'))

def pretty_timedelta(td):
    """ Convert a timedelta to a human readable string """
    if td.days > 0:
        return f"{td.days} days"
    elif td.seconds > 3600:
        return f"{td.seconds // 3600} hours"
    elif td.seconds > 60:
        return f"{td.seconds // 60} minutes"
    else:
        return f"{td.seconds} seconds"

def format_logs(lines, threshold):
    """ Format the logs """
    def format_line(parts):
        try:
            raw_date = parts[0]
            raw_time = parts[1]
            datetime = dt.datetime.strptime(f"{raw_date} {raw_time}", "%Y-%m-%d %H:%M:%S,%f")
            ago = dt.datetime.now() - datetime
            levelname = parts[3]
            message = ' '.join(parts[5:])
        except Exception:
            return f"<pre>{line}</pre>"
        # Color the levelname
        match levelname:
            case "DEBUG":
                levelname = "<span style='color: gray;'>DEBUG  </span>"
            case "INFO":
                levelname = "<span style='color: blue;'>INFO   </span>"
            case "WARNING":
                levelname = "<span style='color: orange;'>WARNING</span>"
            case "ERROR":
                levelname = "<span style='color: red;'>ERROR  </span>"

        if message.startswith("Request") or message.startswith("Response"):
            message = message.replace("http://localhost:5000", "", 1)
            message = message.replace("https://api.smartycope.org", "", 1)
            message = message.replace("Request", "<span style='font-weight: bold'>⬇️  Request</span>", 1)
            message = message.replace("Response", "<span style='font-weight: bold'>🔼 Response</span>", 1)
            message = message.replace("->", "<span style='font-weight: bold'>-></span>", 1)
            message = message.replace("200 OK", "<span style='color: green'>200 OK</span>", 1)


        preamble = f"<span style='color: #dedede;'>{raw_date} {raw_time}</span> {pretty_timedelta(ago)} ago {levelname} "
        return f"{preamble}: {message}"

    spacer_count = 0
    for line in reversed(lines):
        try:
            parts = line.split(' ')
            # It's a spacer
            if len(parts) == 1:
                spacer_count += 1
                yield line + f"<span style='color: #dedede;'>Spacer #{spacer_count}</span>"
                continue
            levelname = parts[3]
            if logging._nameToLevel.get(levelname, 100) >= threshold:
                yield format_line(parts)
        except Exception as err:
            # continue  # skip malformed lines
            # log.error("Failed to format log line: %s", line)
            yield f"Error parsing line: {str(err)}\t{line}"#<br/><pre>{traceback.format_exc().replace('\n', '<br/>')}</pre>"

@bp.delete('/logs/')
def delete_logs():
    with open(current_app.LOG_FILE, 'w') as f:
        f.write("")
    return "Logs cleared", 200

@bp.post('/logs/')
def add_spacer():
    with open(current_app.LOG_FILE, 'a') as f:
        f.write("<hr/>\n")
    return "Spacer added", 200

def get_system_logs():
    try:
        with open("/var/log/syslog", 'r') as f:
            lines = format_logs(f.readlines(), logging._nameToLevel[level])
    except FileNotFoundError:
        lines = ["Log file not found."]
    return render_template('logs_template.html', logs=lines)

def get_reminder_runner_logs():
    try:
        with open("/var/log/reminder-runner.log", 'r') as f:
            lines = format_logs(f.readlines(), logging._nameToLevel[level])
    except FileNotFoundError:
        lines = ["Log file not found."]
    return render_template('logs_template.html', logs=lines)

@bp.get('/logs/<level>/')
def get_logs(level):
    level = level.upper()

    # TODO: something like this probably
    # journalctl -u rock-server.service -q -f
    if level == "SYSTEM":
        return get_system_logs()
    if level == "REMINDERS":
        return get_reminder_runner_logs()
    if level not in logging._nameToLevel:
        return f'Invalid level: {level}', 400

    try:
        with open(current_app.LOG_FILE, 'r') as f:
            lines = format_logs(f.readlines(), logging._nameToLevel[level])
    except FileNotFoundError:
        lines = ["Log file not found."]

    return render_template('logs_template.html', logs=lines)

