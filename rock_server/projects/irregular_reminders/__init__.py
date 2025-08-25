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

# DATABASE = "reminders.db"
# with sqlite3.connect(DATABASE) as con:
#     con.executescript("""BEGIN;
#         CREATE TABLE IF NOT EXISTS reminders (
#             id INTEGER PRIMARY KEY,
#             version,
#             title,
#             message,
#             trigger_work_hours,
#             trigger_min_time,
#             trigger_max_time,
#             trigger_dist,
#             trigger_dist_params,
#             trigger_work_days,
#             repeat,
#             spacing_min,
#             spacing_max,
#             spacing_dist,
#             spacing_dist_params,
#             next_trigger_time,
#             last_trigger_time,
#             alive
#         );
#         CREATE TABLE IF NOT EXISTS devices (
#             id PRIMARY KEY,
#             token,
#             platform,
#             app_version
#         );
#         CREATE TABLE IF NOT EXISTS apikeys (
#             apikey PRIMARY KEY,
#             secret
#         );
#     END;
#     """)

bp = Blueprint("non_standard_reminders", __name__)

log = current_app.logger
# For now?
# cred = credentials.Certificate("./projects/non_standard_reminders/irregular-reminders-firebase-adminsdk-fbsvc-04f85b69cf.json")
# firebase_admin.initialize_app(cred)
# , name="irregular-reminders"




# store tokens in memory (for demo) — in production use a DB
expo_push_tokens = set()

@bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    token = data.get("token")
    if token:
        expo_push_tokens.add(token)
        return {"status": "ok", "stored": token}
    return {"error": "no token"}, 400


@bp.route("/debug", methods=["POST"])
def debug_send():
    data = request.get_json()
    title = data.get("title", "Hello from the server! (default title)")
    body = data.get("body", "(default body from server)")
    seconds = data.get("seconds", 10)
    token = data.get("token")
    data.update({'from server': 'If youre seeing this, it worked!'})

    if token:
        message = {
            "to": token,
            "sound": "default",
            "title": title + " (non-default from server)",
            "body": body + " (non-default from server)",
            # Reply with the original response
            "data": data,
        }
    else:
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

    # return response.json()
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
