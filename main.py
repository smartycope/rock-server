from flask import Flask
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask,  request, jsonify
import sqlite3

app = Flask(__name__)
# app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///apikeys.db"
# app.config["APIKEY_ALLOW_HEADER"] = True  # allow sending API key in headers


# Create DB models
# apikey_manager.init_db()

# with sqlite3.connect("apikeys.db") as con:
    # con.execute("CREATE TABLE IF NOT EXISTS apikeys (apikey PRIMARY KEY, secret)")
    # con.execute("CREATE TABLE IF NOT EXISTS devices (token PRIMARY KEY, platform, app_version)")
    # con.execute("CREATE TABLE IF NOT EXISTS reminders (")


# If we're running on the server, we're not debugging
app.DEBUG = os.uname().nodename != "rockpi-4b"

# Set the logger to debug level because we're filtering later
app.logger.setLevel(logging.DEBUG)

# Set up file-based logging
app.LOG_FILE = 'app.log'
file_handler = RotatingFileHandler(app.LOG_FILE, maxBytes=1024*1024, backupCount=1) # 1MB
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
app.logger.addHandler(file_handler)

with app.app_context():
    from .projects.irregular_reminders import bp as reminders_bp
    app.register_blueprint(reminders_bp, url_prefix="/irregular-reminders")

    # Create a test key if none exists
    # with sqlite3.connect("apikeys.db") as con:
    #     cur = con.cursor()
    #     cur.execute("SELECT * FROM apikeys")
    #     if not (test_key := cur.fetchone()):
    #         cur.execute("INSERT INTO apikeys (apikey) VALUES (?)", ("TEST_KEY",))
    #         test_key = "TEST_KEY"
    #     else:
    #         test_key = test_key[0]
    #     con.commit()

    # print("Test API key:", test_key)

    from .system_endpoints import bp as system_endpoints_bp
    app.register_blueprint(system_endpoints_bp)


if __name__ == "__main__":
    app.logger.info("Server started via main")
    # Gunicorn will handles the server port and IP
    app.run()










