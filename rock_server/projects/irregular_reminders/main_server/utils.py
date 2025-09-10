"""
Functions that aren't endpoints
"""

from datetime import datetime
from sqlite3 import Connection
from flask import current_app
from .Reminder import Reminder
log = current_app.logger

def calculate_next_reminder(con:Connection):
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