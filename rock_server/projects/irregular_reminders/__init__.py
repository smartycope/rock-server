from hmac import HMAC, compare_digest
# import firebase_admin
# from firebase_admin import credentials, messaging

from hashlib import sha256
from time import time
from flask import Blueprint, request, current_app
import sqlite3
from .Reminder import Reminder
from functools import wraps
import os
from time import sleep
import requests
from pydantic import BaseModel, PositiveInt, ValidationError
from typing import Literal

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

def validate_json(schema):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                json = request.get_json()
                obj = schema(**json)
            except ValidationError as e:
                log.error("Validation error: %s", e)
                return {"error": str(e)}, 400
            except Exception as e:
                log.error("likely a JSON parsing error: %s", e)
                return {"error": str(e)}, 400
            else:
                return f(obj, *args, **kwargs)
        return decorated_function
    return decorator


class RegisterDevice(BaseModel):
    token: str
    platform: Literal["ios", "android"]
    app_version: str
    device_id: str

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
        with con.cursor() as cur:
            token = cur.execute(
                "SELECT token FROM devices WHERE device_id = ?",
                (data.device_id,)
            ).fetchone()[0]
    except IndexError:
        log.error("Invalid device_id")
        return {"error": "Invalid device_id"}, 400

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




@bp.route("/debug", methods=["POST"])
def debug_send():
    log.debug("Received reminders debug request")
    data = request.get_json()
    title = data.get("title", "Hello from the server! (default title)")
    body = data.get("body", "(default body from server)")
    seconds = data.get("seconds", 10)
    token = data.get("token")
    data.update({'from server': 'If youre seeing this, it worked!'})

    if token:
        log.info("Sending notification to %s", token)
        message = {
            "to": token,
            "sound": "default",
            "title": title + " (non-default from server)",
            "body": body + " (non-default from server)",
            # Reply with the original response
            "data": data,
        }
    else:
        log.warning("No token provided")
        return {"error": "no token"}, 400

    sleep(seconds)

    # Expo push API endpoint
    response = requests.post(
        "https://exp.host/--/api/v2/push/send",
        json=message,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        timeout=5
    )

    log.info("Response: %s", response.json())
    return {"status": "ok", "response": response.json()}, 200


# def send_reminder(token, reminder:Reminder):
#     message = messaging.Message(
#         notification=messaging.Notification(
#             title=reminder.title,
#             body=reminder.message,
#         ),
#         token=token  # Device token from client
#     )
#     response = messaging.send(message)
#     log.info("Successfully sent:", response)

# def require_apikey(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         apikey = request.headers.get('X-API-Key')
#         if not apikey:
#             return {'error': 'API key required'}, 401
#         return f(*args, **kwargs)
#     return decorated_function


# @bp.route("/debug", methods=["POST"])
# @require_apikey
# def debug_send_immediate_reminder():
#     """ Requires a token and a title and message """
#     log.info("Received debug request")
#     req = request.get_json()
#     try:
#         # Really just using it as a placeholder for now
#         reminder = Reminder(
#             title=req.get("title", "TEST TITLE"),
#             message=req.get("message", "TEST MESSAGE")
#         )
#         send_reminder(req.get("token"), reminder)
#     except Exception as e:
#         log.error("Failed to send immediate reminder:", e)
#         return {"error": str(e)}, 400
#     log.info("Successfully sent immediate reminder:", reminder)
#     return {"status": "Notification sent"}, 200


# @bp.route("/devices/register", methods=["POST"])
# @require_apikey
# def register_device():
#     req = request.get_json()

#     with sqlite3.connect(DATABASE) as con:
#         con.execute(
#             "INSERT INTO devices (token, platform, app_version) VALUES (?, ?, ?)",
#             (req.get("token"), req.get("platform"), req.get("app_version"))
#         )

#     return {"status": "Device registered"}, 200

# @bp.route("/schedule", methods=["POST"])
# @require_apikey
# def schedule_reminder():
#     req = request.get_json()

#     try:
#         reminder = Reminder.deserialize(req)
#     except Exception as e:
#         return {"error": str(e)}, 400

#     with sqlite3.connect(DATABASE) as con:
#         reminder.add_to_db(con)

#     return {"status": "Notification scheduled"}, 200
