import json
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import pytest
from flask import Flask
from . import create_test_app, app, DB

# Test data
# TODO: these should go away in favor of using the examples fixture
TEST_DEVICE_ID = "test-device-123"
TEST_DEVICE_ID2 = "test-device-456"
TEST_TOKEN = "test-token-456"
TEST_TOKEN2 = "test-token-789"
TEST_PLATFORM = "android"
TEST_APP_VERSION = "1"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Accept-encoding": "gzip, deflate",
}
# Probably need to move this somewhere
API_VERSION = 'v1'

@pytest.fixture
def client(app, db):
    """A test client for the app."""
    return app.test_client()

def test_register_device(client):
    """Test device registration."""
    # Test successful registration
    data = {
        "token": TEST_TOKEN,
        "platform": TEST_PLATFORM,
        "app_version": TEST_APP_VERSION
    }

    response = client.post(f'{API_VERSION}/devices/{TEST_DEVICE_ID}',
                         data=json.dumps(data),
                         content_type='application/json')

    assert response.status_code == 200
    assert response.json == {"status": "ok"}

    # Verify the device was added to the database
    with sqlite3.connect(DB) as con:
        cursor = con.cursor()
        cursor.execute("SELECT * FROM devices WHERE device_id = ?", (TEST_DEVICE_ID,))
        device = cursor.fetchone()

        assert device is not None
        assert device[0] == TEST_DEVICE_ID  # device_id
        assert device[1] == TEST_TOKEN      # token
        assert device[2] == TEST_PLATFORM   # platform
        assert device[3] == TEST_APP_VERSION  # app_version
        assert device[4] is not None        # last_updated

    # Test update existing device
    new_token = "new-test-token-789"
    data["token"] = new_token

    response = client.post(f'{API_VERSION}/devices/{TEST_DEVICE_ID}',
                         data=json.dumps(data),
                         content_type='application/json')

    assert response.status_code == 200

    # Verify the token was updated
    with sqlite3.connect(DB) as con:
        cursor = con.cursor()
        cursor.execute("SELECT token FROM devices WHERE device_id = ?", (TEST_DEVICE_ID,))
        token = cursor.fetchone()[0]
        assert token == new_token

def test_schedule_reminder(client):
    """Test scheduling a reminder."""
    # Create a test reminder
    # The client shouldn't pass version or device_id (device_id is in the URL)
    # And for now, at least, version is the same as the API_VERSION in the URL
    reminder_data = {
        "id": str(uuid.uuid4()),
        # "version": 1,
        "title": "Test Reminder",
        "message": "This is a test reminder",
        "work_hours_start": "09:00",
        "work_hours_end": "17:00",
        "work_days": [True, True, True, True, True, False, False],
        "min_time": (datetime.now() - timedelta(days=1)).isoformat(),
        "max_time": (datetime.now() + timedelta(days=7)).isoformat(),
        "dist": "uniform",
        "dist_params": {},
        "repeat": True,
        "spacing_min": "1h",
        "spacing_max": "1d"
    }

    # Test successful reminder creation
    response = client.post(f'{API_VERSION}/reminders/{TEST_DEVICE_ID}',
                          data=json.dumps(reminder_data),
                          headers=HEADERS,
                          content_type='application/json')

    assert response.status_code == 200
    assert response.json == {"status": "ok"}

    # Verify the reminder was added to the database
    with sqlite3.connect(DB) as con:
        cursor = con.cursor()
        cursor.execute("SELECT * FROM reminders WHERE id = ?", (reminder_data["id"],))
        reminder = cursor.fetchone()

        assert reminder is not None
        assert reminder[0] == reminder_data["id"]  # id
        assert reminder[2] == reminder_data["title"]  # title
        assert reminder[3] == reminder_data["message"]  # message
        assert reminder[-1] == TEST_DEVICE_ID  # device_id

def test_get_reminders(client, db, examples):
    """Test retrieving reminders for a device."""

    # Test getting reminders
    response = client.get(f'{API_VERSION}/reminders/{examples["devices"][0]["device_id"]}')

    assert response.status_code == 200
    reminders = response.json

    assert len(reminders) == len(db.execute("SELECT * FROM reminders WHERE device_id = ?", (examples["devices"][0]["device_id"],)).fetchall())
    assert reminders[0]['id'] == examples["reminders"][0]["id"]
    assert reminders[1]['id'] == examples["reminders"][2]["id"]
    assert 'device_id' not in reminders[0]

    # Test getting reminders for non-existent device
    response = client.get(f'{API_VERSION}/reminders/non-existent-device')
    assert response.status_code == 200
    assert response.json == []

def test_update_reminder(client, db, examples):
    """Test updating a reminder."""
    # Test updating the reminder
    update_data = {
        "title": "Updated Test Reminder",
        "message": "This is an updated test reminder"
    }

    # with patch('rock_server.projects.irregular_reminders.calculate_next_reminder') as mock_calculate:
    #     mock_calculate.return_value = MagicMock(id="test-reminder-1")

    response = client.put(f'{API_VERSION}/reminders/{examples["devices"][0]["device_id"]}/{str(examples["reminder_objs"][0].id)}',
        data=json.dumps(update_data),
        headers=HEADERS
    )

    assert response.status_code == 200
    assert response.json == {"status": "ok"}

    # Verify the reminder was updated in the database
    with sqlite3.connect(DB) as con:
        cursor = con.cursor()
        cursor.execute("SELECT title, message FROM reminders WHERE id = ?", (str(examples['reminder_objs'][0].id),))
        title, message = cursor.fetchone()

        assert title == "Updated Test Reminder"
        assert message == "This is an updated test reminder"

def test_delete_reminder(client, db, examples):
    """Test deleting a reminder."""
    response = client.delete(f'{API_VERSION}/reminders/{examples["devices"][0]["device_id"]}/{str(examples["reminder_objs"][0].id)}', headers=HEADERS)

    assert response.status_code == 200
    assert response.json == {"status": "ok"}

    # Verify the reminder was deleted from the database
    with sqlite3.connect(DB) as con:
        cursor = con.cursor()
        cursor.execute("SELECT * FROM reminders WHERE id = ?", (str(examples['reminder_objs'][0].id),))
        reminder = cursor.fetchone()

        assert reminder is None

    # Test deleting a non-existent reminder
    response = client.delete(f'{API_VERSION}/reminders/{examples["devices"][0]["device_id"]}/non-existent-reminder', headers=HEADERS)
    assert response.status_code == 200  # Should still return 200 even if reminder doesn't exist
