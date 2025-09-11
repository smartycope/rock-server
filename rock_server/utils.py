from functools import wraps
from flask import request, current_app
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


def format_line(line):
    try:
        parts = line.split(' ')
        raw_date = parts[0]
        raw_time = parts[1]
        datetime = dt.datetime.strptime(f"{raw_date} {raw_time}", "%Y-%m-%d %H:%M:%S,%f")
        ago = dt.datetime.now() - datetime
        levelname = parts[3]
        message = ' '.join(parts[5:])
    except Exception:
        return f"<pre>{line}</pre>"
    # Color the levelname
    match levelname:
        case "DEBUG":
            levelname = "<span style='color: gray;'>DEBUG  </span>"
        case "INFO":
            levelname = "<span style='color: blue;'>INFO   </span>"
        case "WARNING":
            levelname = "<span style='color: orange;'>WARNING</span>"
        case "ERROR":
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


def format_logs(lines, threshold):
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
                yield format_line(line)
        except Exception as err:
            # continue  # skip malformed lines
            # log.error("Failed to format log line: %s", line)
            yield f"Error parsing line: {str(err)}\t{line}"#<br/><pre>{traceback.format_exc().replace('\n', '<br/>')}</pre>"
