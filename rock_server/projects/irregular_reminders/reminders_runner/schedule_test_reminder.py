import requests
import json
import datetime

run_at = datetime.datetime.now() + datetime.timedelta(seconds=5)
job_data = {
    "id": f"notify-{42}-{int(run_at.timestamp())}",
    "func": "app:send_push_notification",  # module:function
    "args": [42, "Hello from Flask!", "Test Reminder"],
    "trigger": "date",
    "run_date": run_at.isoformat()
}

resp = requests.post("http://localhost:5050/scheduler/jobs", json=job_data)
resp.raise_for_status()

print(json.dumps(requests.get("http://localhost:5050/scheduler/jobs").json(), indent=2))


