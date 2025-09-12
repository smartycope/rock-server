""" Quick manual test script to check if the server and runner are talking to each
other correctly. Meant to be run while both processes are running on the server
"""

import sqlite3
from datetime import datetime, time, timedelta
import requests
# Main flask server
SERVER = "https://api.smartycope.org/irregular-reminders/v1"
# Flask APScheduler process
RUNNER = "http://localhost:5050"
DB = "/home/rock/rock-server/reminders.db"
con = sqlite3.connect(DB)
DEVICE_ID = "__test__"

if __name__ == "__main__":
    # First insert a fake device
    # If it's already there, update it, since that just means we've rerun the script
    con.execute("INSERT OR REPLACE INTO devices (device_id, token, platform, app_version, last_updated) VALUES (?, ?, ?, ?, ?)",
        (DEVICE_ID, "not-a-real-token", "test", "1", datetime.now().isoformat())
    )
    con.commit()

    # Now request a fake reminder
    requests.post(f"{SERVER}/reminders/{DEVICE_ID}", json={
        "title": "Test",
        "message": "Test",
        "work_hours_start": "00:00",
        "work_hours_end": "23:59",
        "work_days": [True] * 7,
        "min_time": "2025-09-11T11:15:00",
        "max_time": "2025-09-11T11:15:00",
        "dist": "uniform",
        "dist_params": {"mean": "1s 1m 1h 1d", "std": "1s 1m 1h 1d"},
        "repeat": True,
        "spacing_min": "1s 1m 1h 1d",
        "spacing_max": "1s 1m 1h 1d"
    })

    # it should show up in the db in 2 places
    assert (reminder := con.execute("SELECT * FROM reminders WHERE device_id = ?", (DEVICE_ID,)).fetchone())
    # job_id is the last column
    assert con.execute("SELECT * FROM jobs WHERE id = ?", (reminder[-1],)).fetchone()

    # it should show up in the runner process
    print(requests.get(f"{RUNNER}/jobs", timeout=5).json())
    print('-' * 20)

    # Get the id of the reminder
    id = reminder[0]

    # Update it
    requests.put(f"{SERVER}/reminders/{DEVICE_ID}/{id}", json={"alive": False}, timeout=5)

    # It should be paused in the runner process
    print(requests.get(f"{RUNNER}/jobs", timeout=5).json())
    print('-' * 20)

    # Delete it
    requests.delete(f"{SERVER}/reminders/{DEVICE_ID}/{id}", timeout=5)

    # It should be deleted in the runner process
    print(requests.get(f"{RUNNER}/jobs", timeout=5).json())