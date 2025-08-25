# rock-server
A catch-all backend for all my projects

## Commands
To recover on the pi:
```bash
cd; ./recover.sh
```
will load a fix from the repo, restart the server, and check the status of the process

To run locally:
```bash
flask --app rock_server/main run --debug
```

or
```bash
python main.py
```
also works, but without debug mode

To update docs:
```bash
pdoc --output-dir static/docs main.py
```