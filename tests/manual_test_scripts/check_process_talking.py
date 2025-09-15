""" Quick manual test script to check if the server and runner are talking to each
other correctly. Meant to be run while both processes are running on the server
"""

import sqlite3
from datetime import datetime, time, timedelta
import requests
import uuid

# Main flask server
SERVER = "https://api.smartycope.org/irregular-reminders/v1"
# Flask APScheduler process
RUNNER = "http://localhost:5050"
DB = "/home/rock/rock-server/reminders.db"
con = sqlite3.connect(DB)
DEVICE_ID = "__test__"
ID = str(uuid.uuid4())

if __name__ == "__main__":
    print('Starting integration tests...')
    print('Inserting fake device...', end=' ')
    # First insert a fake device
    # If it's already there, update it, since that just means we've rerun the script
    con.execute("INSERT OR REPLACE INTO devices (device_id, token, platform, app_version, last_updated) VALUES (?, ?, ?, ?, ?)",
        (DEVICE_ID, "not-a-real-token", "test", "1", datetime.now().isoformat())
    )
    con.commit()
    print('done')
    # Now request a fake reminder
    print('Requesting fake reminder from server...', end=' ')
    requests.post(f"{SERVER}/reminders/{DEVICE_ID}", json={
        "id": ID,
        "title": "Test",
        "message": "Test",
        "work_hours_start": "01:23",
        "work_hours_end": None,
        "work_days": [True] * 7,
        "min_time": datetime.now().isoformat(),
        "max_time": (datetime.now() + timedelta(minutes=1)).isoformat(),
        "dist": "uniform",
        "dist_params": {},
        "repeat": True,
        "spacing_min": "1s 1m 1h 0d",
        "spacing_max": "1s 1m 3h"
    }, timeout=5).raise_for_status()
    print('done')
    # it should show up in the db in 2 places
    assert (reminder := con.execute("SELECT * FROM reminders WHERE device_id = ? AND id = ?", (DEVICE_ID, ID)).fetchone())
    print('Found reminder with id:', ID, 'and it has the job_id:', reminder[-1])
    # print(reminder)
    # job_id is the last column
    assert con.execute("SELECT * FROM jobs WHERE id = ?", (reminder[-1],)).fetchone()
    print('Job is in the jobs table')

    # it should show up in the runner process
    assert (job := requests.get(f"{RUNNER}/scheduler/jobs", timeout=5).json())
    for i in job:
        if i['id'] == reminder[-1]:
            assert i['next_run_time'] == reminder[-2]
            break
    print('Job is in the runner process')
    print()
    print('-' * 20)

    # Update it
    print('Updating fake reminder from server...', end=' ')
    print(requests.put(f"{SERVER}/reminders/{DEVICE_ID}/{ID}", json={"alive": False}, timeout=5))
    print('done')

    # It should be paused in the runner process
    # requests.get(f"{RUNNER}/scheduler/jobs", timeout=5).json()
    print('-' * 20)

    # Delete it
    print('Deleting fake reminder from server...', end=' ')
    requests.delete(f"{SERVER}/reminders/{DEVICE_ID}/{ID}", timeout=5).raise_for_status()
    print('done')

    # It should be deleted in the runner process
    # print(requests.get(f"{RUNNER}/scheduler/jobs", timeout=5).json())