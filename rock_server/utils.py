from functools import wraps
from flask import request, current_app, Response, stream_with_context, url_for, render_template
from time import sleep
from pydantic import ValidationError
import datetime as dt
import logging


log = current_app.logger

def validate_json(schema):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                json = request.get_json()
                obj = schema(**json)
            except ValidationError as e:
                log.error("Validation error: %s", e)
                return {"error": str(e)}, 400
            except Exception as e:
                log.error("likely a JSON parsing error: %s", e)
                return {"error": str(e)}, 400
            print(args)
            print(kwargs)
            return f(obj, *args, **kwargs)
        return decorated_function
    return decorator


def pretty_timedelta(td):
    """ Convert a timedelta to a human readable string """
    if td.days > 0:
        return f"{td.days} days"
    elif td.seconds > 3600:
        return f"{td.seconds // 3600} hours"
    elif td.seconds > 60:
        return f"{td.seconds // 60} minutes"
    else:
        return f"{td.seconds} seconds"


def format_line(line, is_system):
    try:
        # [2025-09-13 16:55:29,220] ...
        # [2025-09-13 16:55:10 -0500] [176625] [INFO] ...
        parts = line.split(' ')
        if is_system:
            raw_date = parts[0][1:]
            if parts[2].startswith('-'):
                parts.pop(2)
                # Also pop the 3rd element, which is now the 2nd element
                parts.pop(2)
                raw_time = parts[1]
                levelname = parts[2].strip('[]')
                datetime = dt.datetime.strptime(f"{raw_date} {raw_time}", "%Y-%m-%d %H:%M:%S")
            else:
                levelname = parts[2]
                raw_time = parts[1][:-1]
            message = ' '.join(parts[4:])
            datetime = dt.datetime.strptime(f"{raw_date} {raw_time}", "%Y-%m-%d %H:%M:%S,%f")
        else:
            raw_date = parts[0]
            raw_time = parts[1]
            levelname = parts[3]
            message = ' '.join(parts[5:])
            datetime = dt.datetime.strptime(f"{raw_date} {raw_time}", "%Y-%m-%d %H:%M:%S,%f")
        ago = dt.datetime.now() - datetime
    except Exception:
        return f"<pre>{line}</pre>"
    # Color the levelname
    if levelname == "DEBUG":
        levelname = "<span style='color: gray;'>DEBUG  </span>"
    elif levelname == "INFO":
        levelname = "<span style='color: blue;'>INFO   </span>"
    elif levelname == "WARNING":
        levelname = "<span style='color: orange;'>WARNING</span>"
    elif levelname == "ERROR":
        levelname = "<span style='color: red;'>ERROR  </span>"

    if message.startswith("Request") or message.startswith("Response"):
        message = message.replace("http://localhost:5000", "", 1)
        message = message.replace("https://api.smartycope.org", "", 1)
        message = message.replace("Request", "<span style='font-weight: bold'>⬇️  Request</span>", 1)
        message = message.replace("Response", "<span style='font-weight: bold'>🔼 Response</span>", 1)
        message = message.replace("->", "<span style='font-weight: bold'>-></span>", 1)
        message = message.replace("200 OK", "<span style='color: green'>200 OK</span>", 1)


    preamble = f"<span style='color: #dedede;'>{raw_date} {raw_time}</span> {pretty_timedelta(ago)} ago {levelname} "
    return f"{preamble}: {message}"


def format_logs(lines, threshold, is_system):
    """ Format the logs """
    spacer_count = 0
    for line in reversed(lines):
        try:
            parts = line.split(' ')
            # It's a spacer
            if len(parts) == 1:
                spacer_count += 1
                yield line + f"<span style='color: #dedede;'>Spacer #{spacer_count}</span>"
                continue
            levelname = parts[3]
            if logging._nameToLevel.get(levelname, 100) >= threshold:
                yield format_line(line, is_system)
        except Exception as err:
            # continue  # skip malformed lines
            # log.error("Failed to format log line: %s", line)
            yield f"Error parsing line: {str(err)}\t{line}"#<br/><pre>{traceback.format_exc().replace('\n', '<br/>')}</pre>"


def generate_log_endpoints(app, log_file, is_system, postfix=''):
    """ Generate endpoints for logging.
        postfix should start with a / and not end with one
    """
    @app.delete(f'/logs{postfix}/')
    def delete_logs():
        with open(log_file, 'w') as f:
            f.write("")
        return "Logs cleared", 200
    delete_logs.__name__ = f"delete_{postfix}_logs"

    @app.post(f'/logs{postfix}/')
    def add_spacer():
        with open(log_file, 'a') as f:
            f.write("<hr/>\n")
        return "Spacer added", 200
    add_spacer.__name__ = f"add_spacer_{postfix}"

    @app.get(f"/logs{postfix}/stream/")
    def stream_logs():
        def generate():
            with open(log_file, 'r') as f:
                f.seek(0, 2)  # move to end of file
                while True:
                    line = f.readline()
                    if line:
                        yield f"data: {format_line(line, is_system)}\n\n"
                    else:
                        sleep(0.25)  # don’t busy loop
        return Response(stream_with_context(generate()), mimetype="text/event-stream")
    stream_logs.__name__ = f"stream_{postfix}_logs"

    @app.get(f'/logs{postfix}/<level>/')
    def get_logs(level):
        level = level.upper()

        if level not in logging._nameToLevel:
            return f'Invalid level: {level}', 400

        try:
            with open(log_file, 'r') as f:
                lines = format_logs(f.readlines(), logging._nameToLevel[level], is_system)
        except FileNotFoundError:
            lines = ["Log file not found."]


        return render_template('logs_template.html',
            logs=lines,
            clear_endpoint=url_for(f"{app.name}.delete_{postfix}_logs"),
            # clear_endpoint=f'/logs{postfix}/',
            add_spacer_endpoint=url_for(f"{app.name}.add_spacer_{postfix}"),
            # add_spacer_endpoint=f'/logs{postfix}/',
            stream_endpoint=url_for(f"{app.name}.stream_{postfix}_logs")
            # stream_endpoint=f'/logs{postfix}/stream/'
        )
    get_logs.__name__ = f"get_{postfix}_logs"

    return get_logs, stream_logs, add_spacer, delete_logs
