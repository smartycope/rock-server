from flask import Flask
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask,  request, jsonify, render_template
# import sqlite3

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
# app.DEBUG = os.uname().nodename != "rockpi-4b"
# NOTE: this is actually built in, so...
app.DEBUG = app.debug

# For irregular reminders
# TODO: this should be moved to the config
app.DATABASE = "reminders.db"
app.config['DATABASE'] = "reminders.db"

# Set the logger to debug level because we're filtering later
app.logger.setLevel(logging.DEBUG)

# Set up file-based logging
app.LOG_FILE = 'app.log'
file_handler = RotatingFileHandler(app.LOG_FILE, maxBytes=1024*1024, backupCount=1) # 1MB
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
app.logger.addHandler(file_handler)


with app.app_context():
    @app.before_request
    def log_request_info():
        """ Log all requests """
        app.logger.debug("Request: %s %s", request.method, request.url)

    @app.after_request
    def log_response(response):
        app.logger.debug("Response: %s %s -> %s", request.method, request.url, response.status)
        return response

    @app.errorhandler(Exception)
    def log_error(e):
        app.logger.exception("Error handling request: %s %s %s", request.method, request.url, str(e))
        return "Internal server error", 500

    @app.errorhandler(404)
    def log_404(e):
        app.logger.warning("404 Not Found: %s %s", request.method, request.url)
        return render_template('error.html', error=e), 404


    from rock_server.projects.irregular_reminders.main_server import bp as reminders_bp
    app.register_blueprint(reminders_bp, url_prefix="/irregular-reminders")

    from rock_server.projects.customized_form import bp as customized_form_bp
    app.register_blueprint(customized_form_bp, url_prefix="/customized-form")

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

    from rock_server.system_endpoints import bp as system_endpoints_bp
    app.register_blueprint(system_endpoints_bp)


if __name__ == "__main__":
    app.logger.info("Server started via main")
    # Gunicorn will handles the server port and IP
    app.run()



# TODO:
# Left off with the flask server giving 404s when it shouldn't
