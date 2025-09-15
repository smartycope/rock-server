import logging
import traceback
import sqlite3
from time import time, sleep
from typing import Literal

from flask import Blueprint, current_app, render_template, request, url_for, Response, stream_with_context
from pydantic import BaseModel, ValidationError

from rock_server.utils import format_logs, validate_json, format_line, generate_log_endpoints

from .Reminder import Reminder
from .utils import (send_to_reminder_runner, update_reminder_runner, delete_from_reminder_runner, format_pydantic_errors)

# This should start the reminder thread

bp = Blueprint("non_standard_reminders", __name__)
log = current_app.logger
DB = current_app.config['DATABASE']
OUR_LOGS = "rock_server/projects/irregular_reminders/reminders_runner/reminder_runner.log"

with sqlite3.connect(DB) as con:
    con.executescript("""BEGIN;
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            next_run_time,
            job_state
        );
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            token,
            platform,
            app_version,
            last_updated
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id TEXT PRIMARY KEY,
            version,
            title,
            message,
            work_hours_start,
            work_hours_end,
            work_days,
            min_time,
            max_time,
            dist,
            dist_params,
            repeat,
            spacing_min,
            spacing_max,
            alive,
            last_trigger_time,
            next_trigger_time,
            device_id,
            job_id,
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL, -- If the job goes off, we need to know
            FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE -- If the device somehow gets deleted (which it isn't set to do), delete all associated reminders
        );
    END;""")

VERSION = 1
API_VERSION = f"v{VERSION}"
ENDPOINTS = {
    'scheduleReminder': f"/{API_VERSION}/reminders/<device_id>",
    'getReminders':     f"/{API_VERSION}/reminders/<device_id>",
    'deleteReminder':   f"/{API_VERSION}/reminders/<device_id>/<id>",
    'updateReminder':   f"/{API_VERSION}/reminders/<device_id>/<id>",
    'register':         f"/{API_VERSION}/devices/<device_id>",
}

class RegisterDeviceValidator(BaseModel):
    token: str
    platform: Literal["ios", "android"]
    app_version: str

# The order of the decorators is important
@bp.post(ENDPOINTS["register"])
# @validate_json(RegisterDeviceValidator)
# NOTE: this is cursed. I'm purely doing it out of curiosity (and to flex)
@validate_json(type("RegisterDeviceValidator2", (BaseModel,), {"__annotations__": {
    "token": str,
    "platform": Literal["ios", "android"],
    "app_version": str,
}}))
def register_device(data, device_id: str):
    """ Register is a misnomer: it registers first, every time after that it's an update """
    with sqlite3.connect(DB) as con:
        con.execute(
            # If it's already registered, update the token
            "INSERT OR REPLACE INTO devices (device_id, token, platform, app_version, last_updated) VALUES (?, ?, ?, ?, ?)",
            (device_id, data.token, data.platform, data.app_version, time())
        )
    log.info("Registered device: %s to token: %s", device_id, data.token)

    return {"status": "ok"}, 200

@bp.post(ENDPOINTS["scheduleReminder"])
def schedule_reminder(device_id: str):
    """ Receive a reminder and add it to the db """
    log.debug("Received reminders schedule request")
    try:
        reminder = Reminder(**request.json, device_id=device_id, version=VERSION)
    except ValidationError as e:
        log.error("Failed to validate reminder: %s", e.errors())
        errs = format_pydantic_errors(e)
        return {"errors": errs}, 400
    except Exception as e:
        log.error("Failed to create reminder entirely: %s", e)
        return {"error": str(e), "traceback": traceback.format_exc()}, 500
    log.debug("Reminder validated: %s", reminder)

    # Send it to the runner process first, so we can attach a job_id
    reminder = send_to_reminder_runner(reminder)
    log.debug("Reminder sent to runner: %s", reminder)

    with sqlite3.connect(DB) as con:
        reminder.load_to_db(con)
    log.debug("Reminder added to db: %s", reminder)

    return {"status": "ok"}, 200

@bp.patch(ENDPOINTS["updateReminder"])
def update_reminder(device_id: str, id):
    """ Set a reminder to alive or dead """
    if len(request.json) == 0:
        return 20

    with sqlite3.connect(DB) as con:
        # I don't see a reason this shouldn't work?
        try:
            reminder = Reminder.load_from_db(con, id)
        except ValueError:
            log.error("Failed to update reminder with id %s: Reminder not found", id)
            return {"error": "Reminder not found"}, 410
        try:
            reminder = reminder.get_modified(request.json)
        except ValidationError as e:
            log.error("Failed to update reminder with id %s: %s", id, e.errors())
            errs = format_pydantic_errors(e)
            return {"errors": errs}, 400

        log.debug("Reminder updated: %s", reminder)

        reminder.load_to_db(con)

        # This does work, but the above is cleaner
        """
        # Create the SET clause with placeholders
        set_clause = ', '.join([f"{k} = ?" for k in request.json.keys()])
        # Execute the update with values in the correct order
        con.execute(
            f"UPDATE reminders SET {set_clause} WHERE id = ? AND device_id = ?",
            (*request.json.values(), str(id), device_id)
        ) """

    # don't forget to update the runner process
    update_reminder_runner(reminder)

    return {"status": "ok"}, 200

@bp.delete(ENDPOINTS["deleteReminder"])
def delete_reminder(device_id: str, id: str):
    """ Delete a reminder from the db """
    # We need the reminder instance to delete it from the runner process, because it needs the job_id FK
    with sqlite3.connect(DB) as con:
        try:
            delete_from_reminder_runner(Reminder.load_from_db(con, id))
        except ValueError:
            log.error("Failed to delete reminder with id %s: Reminder not found", id)
            return {"error": "Reminder not found"}, 410
        except Exception as e:
            log.error("Failed to delete reminder with id %s: %s", id, e)
            return {"error": str(e)}, 500

        con.execute(
            "DELETE FROM reminders WHERE id = ? AND device_id = ?",
            (str(id), device_id)
        )

    log.info("Deleted reminder with id %s", id)

    return {"status": "ok"}, 200

@bp.get(ENDPOINTS["getReminders"])
def get_reminders(device_id: str):
    """ Get all reminders for a device """
    # Remove device_id from the result
    # Darn sqlite3 doesn't support EXCLUDE
    # return con.execute("SELECT * EXCLUDE (device_id) FROM reminders WHERE device_id = ?", (device_id,)).fetchall()
    with sqlite3.connect(DB) as con:
        # cols = [row[1] for row in con.execute("PRAGMA table_info(reminders)") if row[1] != "device_id"]
        # All deserializing does is basically adds dictionary keys to a tuple
        data = [Reminder.from_db(row).serialize(False) for row in con.execute("SELECT * FROM reminders WHERE device_id = ?", (device_id,)).fetchall()]
        log.debug("Returning %s reminders for device %s", len(data), device_id)
        return data




# Logs
generate_log_endpoints(bp, OUR_LOGS, True)
# @bp.delete('/logs/')
# def delete_logs():
#     with open(OUR_LOGS, 'w') as f:
#         f.write("")
#     return "Logs cleared", 200

# @bp.post('/logs/')
# def add_spacer():
#     with open(OUR_LOGS, 'a') as f:
#         f.write("<hr/>\n")
#     return "Spacer added", 200

# @bp.get("/logs/stream")
# def stream_logs():
#     def generate():
#         with open(OUR_LOGS, 'r') as f:
#             f.seek(0, 2)  # move to end of file
#             while True:
#                 line = f.readline()
#                 if line:
#                     yield f"data: {format_line(line)}\n\n"
#                 else:
#                     sleep(0.25)  # don’t busy loop
#     return Response(stream_with_context(generate()), mimetype="text/event-stream")

# @bp.get('/logs/<level>/')
# def get_logs(level):
#     level = level.upper()

#     if level not in logging._nameToLevel:
#         return f'Invalid level: {level}', 400

#     try:
#         with open(OUR_LOGS, 'r') as f:
#             lines = format_logs(f.readlines(), logging._nameToLevel[level])
#     except FileNotFoundError:
#         lines = ["Log file not found."]

#     return render_template('logs_template.html',
#         logs=lines, clear_endpoint=url_for(".delete_logs"),
#         add_spacer_endpoint=url_for(".add_spacer"),
#         stream_endpoint=url_for(".stream_logs")
#     )
