"""
A thread that watches for reminders to trigger. This gets run by systemd in a seperate process.
It communicates with the main app via a single localhost endpoint.
It does:
* Receive the next reminder to trigger from the main app
* Send a push notification to the device at the appropriate time
* Once it's sent a push notification, send a request to the main app to mark it as triggered. After that, the
    main app calculates the next reminder to trigger and sends it's info to this process.
* Start it's own Flask process to handle the requests from the main app
It doesn't:
* Calculate the next time to trigger
* Touch the DB at all
* Have access to Reminder (it just uses some of the reminder's info directly)
"""

import requests
from flask import Flask
from logging.handlers import RotatingFileHandler
import logging
from flask_apscheduler import APScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
import sqlite3

app = Flask(__name__)

DB = "reminders.db"
log = app.logger
LOG_FILE = 'reminder_thread.log'
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1024*1024, backupCount=1) # 1MB
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
app.logger.addHandler(file_handler)


class Config:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']
    SCHEDULER_JOBSTORES = {"default": SQLAlchemyJobStore(url=f"sqlite:///{DB}", tablename='jobs')}
    # SCHEDULER_EXECUTORS = {"default": {"type": "threadpool", "max_workers": 8}}
    # SCHEDULER_JOB_DEFAULTS = {"coalesce": False, "max_instances": 3}
    SCHEDULER_API_ENABLED = True
    # TODO:
    # SCHEDULER_TIMEZONE = 'UTC'

app.config.from_object(Config)
scheduler = APScheduler()


def get_token(device_id: str, con:sqlite3.Connection):
    """ Get a device's token from the database """
    try:
        token = con.execute(
            "SELECT token FROM devices WHERE device_id = ?",
            (device_id,)
        ).fetchone()[0]
    except IndexError:
        log.error("Invalid device_id")
        return # {"error": "Invalid device_id"}, 403
    except Exception as e:
        log.error("Failed to get token: %s", e)
        return # {"error": str(e)}, 500
    return token

def send_push_notification(device_id, title, message):
    """ Send a push notification to a device """
    log.info("⬆️ Sending Push Notification to %s: %s", device_id, title)

    with sqlite3.connect(DB) as con:
        token = get_token(device_id, con)

    if token is None:
        log.error("Failed to get token for device %s", device_id)
        return

    log.debug("Token for push notification: %s", token)

    # Expo push API endpoint
    response = requests.post(
        "https://exp.host/--/api/v2/push/send",
        json={
            "to": token,
            "sound": "default",
            "title": title,
            "body": message,
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        timeout=5
    )
    log.info("✅ Push Notification Response from expo server: %s", response.json())


# Health check
@app.route("/")
def index():
    return {"status": "ok"}, 200


scheduler.init_app(app)
scheduler.start()

if __name__ == "__main__":
    app.run(host="localhost", port=5050)


