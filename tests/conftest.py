import sqlite3
from datetime import datetime, timedelta, time
import pytest
from flask import Flask
import uuid
import json

DB = "test.db"

def create_test_app():
    """Create and configure a test Flask app."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['DATABASE'] = DB

    with app.app_context():
        from rock_server.projects.irregular_reminders import bp as irregular_reminders_bp
        # Register the blueprint
        app.register_blueprint(irregular_reminders_bp)

    # Create test client
    client = app.test_client()

    return app, client

@pytest.fixture
def app():
    """Create and configure a test Flask app."""
    app, _ = create_test_app()
    yield app

@pytest.fixture
def examples(app):
    # Need to be in this order:
    # 'id', 'version', 'title', 'message', 'work_hour', 'work_days',
    # 'min_time', 'max_time', 'dist', 'dist_params', 'repeat', 'spacing_min',
    # 'spacing_max', 'alive', 'last_trigger_time', 'next_trigger_time',
    # 'device_id'
    dev_id1 = str(uuid.uuid4())
    dev_id2 = str(uuid.uuid4())
    data = {
        "reminders": [
            {
                "id": str(uuid.uuid4()),
                "version": 1,
                "title": "Test Reminder",
                "message": "This is a test reminder",
                "work_hours": None,
                "work_days": [True, True, True, True, True, False, False],
                "min_time": (datetime.now() - timedelta(seconds=1)),
                "max_time": (datetime.now() + timedelta(seconds=7)),
                "dist": "uniform",
                "dist_params": {},
                "repeat": True,
                "spacing_min": timedelta(hours=1),
                "spacing_max": timedelta(days=1, seconds=5, minutes=1),
                "alive": True,
                "last_trigger_time": None,
                "next_trigger_time": None,
                "device_id": dev_id1
            },
            {
                "id": str(uuid.uuid4()),
                "version": 1,
                "title": "Test Reminder 2",
                "message": "This is a second test reminder",
                "work_hours": [time(9, 0), time(17, 0)],
                "work_days": [True, True, True, True, True, False, False],
                "min_time": (datetime.now() - timedelta(days=1)),
                "max_time": (datetime.now() + timedelta(days=7)),
                "dist": "normal",
                "dist_params": {"mean": timedelta(hours=1), "std": timedelta(minutes=20)},
                "repeat": False,
                "spacing_min": None,
                "spacing_max": None,
                "alive": True,
                "last_trigger_time": None,
                "next_trigger_time": None,
                "device_id": dev_id2
            },
            {
                "id": str(uuid.uuid4()),
                "version": 1,
                "title": "Test Reminder 2",
                "message": "This is a second test reminder",
                "work_hours": [time(9, 0), time(17, 0)],
                "work_days": [True, True, True, True, True, False, False],
                "min_time": (datetime.now() - timedelta(minutes=1)),
                "max_time": None,
                "dist": "exponential",
                "dist_params": {"mean": timedelta(seconds=5)},
                "repeat": True,
                "spacing_min": "1h",
                "spacing_max": None,
                "alive": False,
                "last_trigger_time": None,
                "next_trigger_time": None,
                "device_id": dev_id1
            }
        ],
        "devices": [
            {
                "device_id": dev_id1,
                "token": "test-token-456",
                "platform": "android",
                "app_version": "1.0.0",
                "last_updated": (datetime.now() - timedelta(days=2)).isoformat()
            },
            {
                "device_id": dev_id2,
                "token": "test-token-789",
                "platform": "ios",
                "app_version": "1.0.0",
                "last_updated": (datetime.now() - timedelta(days=1)).isoformat()
            }
        ]
    }

    with app.app_context():
        from rock_server.projects.irregular_reminders import Reminder
    data['reminder_objs'] = [Reminder(**x) for x in data['reminders']]

    yield data

@pytest.fixture
def db(app, examples):
    """Create and configure a test database."""
    with app.app_context():
        # Set up the database
        with sqlite3.connect(DB) as con:
            # Create tables (same as in __init__.py)
            con.executescript("""
                BEGIN;
                DROP TABLE IF EXISTS devices;
                DROP TABLE IF EXISTS reminders;
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
            # Add a test device
            con.executemany(f"INSERT INTO devices {tuple(examples['devices'][0].keys())} VALUES (?, ?, ?, ?, ?)", [list(i.values()) for i in examples['devices']])
            # Insert a couple reminders into the DB for testing
            con.executemany(f"INSERT INTO reminders {tuple(examples['reminders'][0].keys())} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [list(i.serialize().values()) for i in examples['reminder_objs']])

    yield con