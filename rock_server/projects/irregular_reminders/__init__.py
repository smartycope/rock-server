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
con = sqlite3.connect(DATABASE)

with con:
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

# NOTE: this url_prefix is set by main.py
API_URL = "https://api.smartycope.org/irregular-reminders"
ENDPOINTS = {
    'scheduleReminder':  API_URL + "/reminders/<device_id>",
    'getReminders':      API_URL + "/reminders/<device_id>",
    'deleteReminder':    API_URL + "/reminders/<device_id>/<id>",
    'updateReminder':    API_URL + "/reminders/<device_id>/<id>",
    'register':          API_URL + "/devices/<device_id>",
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
def register_device(device_id: str, data):
    """ Register is a misnomer: it registers first, every time after that it's an update """
    con.execute(
        # If it's already registered, update the token
        "INSERT OR REPLACE INTO devices (device_id, token, platform, app_version, last_updated) VALUES (?, ?, ?, ?, ?)",
        (device_id, data.token, data.platform, data.app_version, time())
    )
    con.commit()
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
    con.execute(
        f"INSERT INTO reminders {'?, ' * len(data)} VALUES ({'?, ' * len(data)})",
        (*data.keys(), *data.values())
    )
    con.commit()

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
    con.execute(
        f"UPDATE reminders SET {'? '*len(request.json.keys())} = {'? '*len(request.json.values())} WHERE id = ? AND device_id = ?",
        (*request.json.keys(), *request.json.values(), str(id), device_id)
    )
    con.commit()

    if next_reminder.id == id:
        next_reminder = calculate_next_reminder(con)

    return {"status": "ok"}, 200

@bp.delete(ENDPOINTS["deleteReminder"])
def delete_reminder(device_id: str, id):
    """ Delete a reminder from the db """
    global next_reminder
    log.debug("Deleting reminder %s", id)
    con.execute(
        "DELETE FROM reminders WHERE id = ? AND device_id = ?",
        (str(id), device_id)
    )
    con.commit()
    if next_reminder.id == id:
        next_reminder = calculate_next_reminder(con)
    return {"status": "ok"}, 200

@bp.get(ENDPOINTS["getReminders"])
def get_reminders(device_id: str):
    """ Get all reminders for a device """
    # Remove device_id from the result
    return con.execute("SELECT * EXCLUDE (device_id) FROM reminders WHERE device_id = ?", (device_id,)).fetchall()