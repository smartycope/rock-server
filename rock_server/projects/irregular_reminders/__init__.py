import sqlite3
from time import time
from typing import Literal

from flask import Blueprint, current_app, request
from pydantic import BaseModel, ValidationError

from rock_server.utils import validate_json

from .Reminder import Reminder
from .globals import DATABASE, next_reminder
# This should start the reminder thread
from .reminder_thread import calculate_next_reminder

bp = Blueprint("non_standard_reminders", __name__)
log = current_app.logger

with sqlite3.connect(DATABASE) as con:
    con.executescript("""BEGIN;
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
            work_hours,
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
            FOREIGN KEY (device_id) REFERENCES devices(device_id)
        );
    END;
    """)

ENDPOINTS = {
    'scheduleReminder': "/reminders/<device_id>",
    'getReminders':     "/reminders/<device_id>",
    'deleteReminder':   "/reminders/<device_id>/<id>",
    'updateReminder':   "/reminders/<device_id>/<id>",
    'register':         "/devices/<device_id>",
}

print(ENDPOINTS)

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
    with sqlite3.connect(DATABASE) as con:
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
    global next_reminder

    log.debug("Received reminders schedule request")
    try:
        reminder = Reminder(**request.json, device_id=device_id)
    except ValidationError as e:
        log.error("Failed to validate reminder: %s", e.errors())
        return {"errors": e.errors()}, 400

    data = reminder.serialize()
    with sqlite3.connect(DATABASE) as con:
        con.execute(
            f"INSERT INTO reminders {'?, ' * len(data)} VALUES ({'?, ' * len(data)})",
            (*data.keys(), *data.values())
        )

    if next_reminder is None or reminder.next_trigger_time < next_reminder.next_trigger_time:
        next_reminder = reminder
        log.debug("Next reminder changed to %s", next_reminder)

    return {"status": "ok"}, 200

@bp.put(ENDPOINTS["updateReminder"])
def update_reminder(device_id: str, id):
    """ Set a reminder to alive or dead """
    log.debug("Updating reminder %s", id)
    if len(request.json) == 0:
        return 201
    with sqlite3.connect(DATABASE) as con:
        con.execute(
            f"UPDATE reminders SET {'? '*len(request.json.keys())} = {'? '*len(request.json.values())} WHERE id = ? AND device_id = ?",
            (*request.json.keys(), *request.json.values(), str(id), device_id)
        )

    if next_reminder.id == id:
        next_reminder = calculate_next_reminder(con)

    return {"status": "ok"}, 200

@bp.delete(ENDPOINTS["deleteReminder"])
def delete_reminder(device_id: str, id):
    """ Delete a reminder from the db """
    global next_reminder
    log.debug("Deleting reminder %s", id)
    with sqlite3.connect(DATABASE) as con:
        con.execute(
            "DELETE FROM reminders WHERE id = ? AND device_id = ?",
            (str(id), device_id)
        )
    if next_reminder.id == id:
        next_reminder = calculate_next_reminder(con)
    return {"status": "ok"}, 200

@bp.get(ENDPOINTS["getReminders"])
def get_reminders(device_id: str):
    """ Get all reminders for a device """
    # Remove device_id from the result
    # Darn sqlite3 doesn't support EXCLUDE
    # return con.execute("SELECT * EXCLUDE (device_id) FROM reminders WHERE device_id = ?", (device_id,)).fetchall()
    with sqlite3.connect(DATABASE) as con:
        cols = [row[1] for row in con.execute("PRAGMA table_info(reminders)") if row[1] != "device_id"]
        return con.execute(f"SELECT {', '.join(cols)} FROM reminders WHERE device_id = ?", (device_id,)).fetchall()
