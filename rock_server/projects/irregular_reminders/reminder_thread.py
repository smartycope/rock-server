import sqlite3
from threading import Thread
from time import sleep
from datetime import datetime, timedelta

import requests
from flask import current_app
from .Reminder import Reminder
from .globals import next_reminder

log = current_app.logger
DB = current_app.config['DATABASE']

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

def send_push_notification(device_id: str, reminder: Reminder, con:sqlite3.Connection):
    """ Send a push notification to a device """
    # Expo push API endpoint
    token = get_token(device_id, con)
    if token is None:
        return

    response = requests.post(
        "https://exp.host/--/api/v2/push/send",
        json={
            "to": token,
            "sound": "default",
            "title": reminder.title,
            "body": reminder.message,
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        timeout=5
    )

    log.debug("Send Push Notification Response from expo server: %s", response.json())

def calculate_next_reminder(con:sqlite3.Connection):
    """ Calculate the next reminder to trigger """
    with con:
        soonest = con.execute(
            "SELECT * FROM reminders WHERE alive = 1 ORDER BY next_trigger_time ASC LIMIT 1"
        ).fetchone()
        if soonest is None:
            log.debug("No reminders found")
            return None
        n = Reminder.from_db(soonest)
        log.info("Next reminder is %s, set to go off in %s", n, n.next_trigger_time - datetime.now())
        return n

def watch_for_reminders():
    """ I don't expect more than 1 second resolution (realistically, 1 minute resolution, but aim for 1s)
        Note that this thread doesn't (and I thiiiink can't?) have access to the current app context
    """
    global next_reminder
    # Connections aren't thread safe
    threaded_con = sqlite3.connect(DB)
    while True:
        if next_reminder is None:
            sleep(1)
            continue

        # Wait until the next trigger time
        # the -1s is so they're all slightly early instead of slightly late (call it HTTP delays)
        # The fudge factor gets handled by Reminder.allowed_resolution_sec
        if next_reminder.next_trigger_time >= datetime.now() - timedelta(seconds=1):
            # ...But don't actually, cause we want to keep checking if next_trigger_time has changed
            # There's probably a more efficient way to do this (Pipe?) but it really doesn't matter that much
            sleep(min((next_reminder.next_trigger_time - datetime.now()).total_seconds(), 1))
        else:
            if next_reminder.trigger_if_ready(threaded_con):
                log.info("Triggering reminder from watchdog thread: %s", next_reminder.id)
                send_push_notification(next_reminder.device_id, next_reminder, threaded_con)
                next_reminder = calculate_next_reminder(threaded_con)
            else:
                log.error("We messed up, reminder %s is not ready to trigger, but we think it is", next_reminder.id)

# if current_app.config.get("DEBUG"):
# if current_app.DEBUG:
# Starting a thread messes up werkzeug's hot reloading
# The testing is just to get it play nice with pytest (it works fine, it just doesnt want to stop)
if not current_app.debug and not current_app.testing:
    # Reeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
    reminder_trigger_thread = Thread(target=watch_for_reminders)
    reminder_trigger_thread.start()
