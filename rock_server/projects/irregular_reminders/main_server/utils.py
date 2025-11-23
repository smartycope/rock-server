"""
Functions that aren't endpoints
"""

from datetime import datetime
from sqlite3 import Connection
import requests
from flask import current_app
from .Reminder import Reminder

log = current_app.logger
RUNNER_URL = "http://localhost:5050"

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

def get_token(device_id: str, con:Connection):
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

def format_pydantic_errors(err):
    errs = err.errors()
    # This is all the client cares about
    return [info['msg'] for info in errs]

# Communication with the runner process
# https://viniciuschiele.github.io/flask-apscheduler/rst/api.html for details
def pause_job(job_id: str):
    try:
        requests.post(f"{RUNNER_URL}/scheduler/jobs/{job_id}/pause", timeout=5).raise_for_status()
        log.debug("Paused dead reminder with id %s", job_id)
    except Exception as e:
        log.error("Failed to pause reminder with id %s: %s", job_id, e)

def resume_job(job_id: str):
    try:
        requests.post(f"{RUNNER_URL}/scheduler/jobs/{job_id}/resume", timeout=5).raise_for_status()
        log.debug("Resumed dead reminder with id %s", job_id)
    except Exception as e:
        log.error("Failed to resume reminder with id %s: %s", job_id, e)

def send_to_reminder_runner(reminder:Reminder):
    """ Send a reminder to be scheduled with the reminders_runner process """
    job_data = {
        "id": f"notify-{reminder.id}",
        "func": "app:send_push_notification",
        "args": [reminder.device_id, reminder.title, reminder.message],
        "trigger": "date",
        "run_date": reminder.next_trigger_time.isoformat()
    }
    try:
        resp = requests.post(f"{RUNNER_URL}/scheduler/jobs", json=job_data, timeout=5)
        resp.raise_for_status()
        resp_json = resp.json()
        reminder.job_id = resp_json['id']
        log.info("Successfully sent reminder with id %s to be scheduled for %s with job id %s", reminder.id, resp_json['run_date'], resp_json['id'])
    except Exception as e:
        log.error("Failed to send reminder to be scheduled: %s", e)
        return

    # If it's dead, pause it
    if not reminder.alive:
        pause_job(reminder.job_id)

    return reminder

def update_reminder_runner(reminder:Reminder):
    """ Update a reminder in the reminders_runner process """
    job_data = {
        # "id": f"notify-{reminder.id}",
        "func": "app:send_push_notification",
        "args": [reminder.device_id, reminder.title, reminder.message],
        "trigger": "date",
        "run_date": reminder.next_trigger_time.isoformat()
    }
    try:
        resp = requests.patch(f"{RUNNER_URL}/scheduler/jobs/{reminder.job_id}", json=job_data, timeout=5)
        resp.raise_for_status()
        log.info("Successfully updated reminder with id %s", reminder.id)
    except Exception as e:
        log.error("Failed to update reminder with id %s: %s", reminder.id, e)
        return

    # If we've change alive, pause or resume it. I assume pausing a paused reminder doesn't do anything
    if reminder.alive:
        resume_job(reminder.job_id)
    else:
        pause_job(reminder.job_id)

def delete_from_reminder_runner(reminder:Reminder):
    """ Delete a reminder from the reminders_runner process """
    try:
        resp = requests.delete(f"{RUNNER_URL}/scheduler/jobs/{reminder.job_id}", timeout=5)
        resp.raise_for_status()
        log.info("Successfully deleted reminder with id %s", reminder.id)
    except Exception as e:
        log.error("Failed to delete reminder with id %s: %s", reminder.id, e)
        return

def clear_all_from_reminder_runner(device_id: str, con:Connection, just_inactive):
    """ Delete all reminders for a device from the reminders_runner process """
    query = "SELECT job_id FROM reminders WHERE device_id = ?"
    if just_inactive:
        query += " AND alive = False"
    for row in con.execute(query, (device_id,)).fetchall():
        delete_from_reminder_runner(Reminder.load_from_db(con, row[0]))
    log.info("Successfully deleted all reminders for device %s", device_id)
