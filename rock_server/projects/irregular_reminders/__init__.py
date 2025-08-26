import os
import sqlite3
from functools import wraps
from time import sleep, time
from typing import Literal

import requests
from flask import Blueprint, current_app, request
from pydantic import BaseModel, PositiveInt, ValidationError

from rock_server.utils import validate_json

from .Reminder import Reminder

DATABASE = "devices.db"
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
    END;
    """)

bp = Blueprint("non_standard_reminders", __name__)

log = current_app.logger


class RegisterDevice(BaseModel):
    token: str
    platform: Literal["ios", "android"]
    app_version: str
    device_id: str

# The order of the decorators is important
@bp.route("/devices/register", methods=["POST"])
@validate_json(RegisterDevice)
def register(data: RegisterDevice):
    """ Register is a misnomer: it registers first, every time after that it's an update """
    # If it's already registered, update the token
    con.execute(
        "INSERT OR REPLACE INTO devices (device_id, token, platform, app_version, last_updated) VALUES (?, ?, ?, ?, ?)",
        (data.device_id, data.token, data.platform, data.app_version, time())
    )
    con.commit()
    log.info("Registered device: %s to token: %s", data.device_id, data.token)

    return {"status": "ok"}, 200

# This will change eventually
class ScheduleReminder(BaseModel):
    reminder: dict[str, str]
    device_id: str
    seconds: int

@bp.route("/schedule", methods=["POST"])
@validate_json(ScheduleReminder)
def schedule(data: ScheduleReminder):
    log.debug("Received reminders schedule request")
    # reminder = data.reminder
    # reminder.add_to_db(con)

    try:
        token = con.execute(
            "SELECT token FROM devices WHERE device_id = ?",
            (data.device_id,)
        ).fetchone()[0]
    except IndexError:
        log.error("Invalid device_id")
        return {"error": "Invalid device_id"}, 400
    except Exception as e:
        log.error("Failed to set token: %s", e)
        return {"error": str(e)}, 500

    log.debug("Sending notification to %s", token)

    sleep(data.seconds)

    # Expo push API endpoint
    response = requests.post(
        "https://exp.host/--/api/v2/push/send",
        json={
            "to": token,
            "sound": "default",
            "title": data.reminder.get("title", "Default title"),
            "body": data.reminder.get("message", "Default message"),
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        timeout=5
    )

    log.debug("Response: %s", response.json())

    return {"status": "ok"}, 200
