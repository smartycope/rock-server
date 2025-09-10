import requests
import json
import datetime
import argparse


parser = argparse.ArgumentParser()
parser.add_argument("device_id", type=str)
parser.add_argument("--seconds", type=int, default=5)
parser.add_argument("--title", type=str, default="Test Reminder")
parser.add_argument("--message", type=str, default="Hello world!")
args = parser.parse_args()

run_at = datetime.datetime.now() + datetime.timedelta(seconds=args.seconds)
job_data = {
    "id": f"notify-{args.device_id}-{int(run_at.timestamp())}",
    "func": "app:send_push_notification",
    "args": [args.device_id, args.title, args.message],
    "trigger": "date",
    "run_date": run_at.isoformat()
}

resp = requests.post("http://localhost:5050/scheduler/jobs", json=job_data)
resp.raise_for_status()

print(json.dumps(requests.get("http://localhost:5050/scheduler/jobs").json(), indent=2))


