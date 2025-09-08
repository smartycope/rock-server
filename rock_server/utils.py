from functools import wraps
from flask import request, current_app
from pydantic import ValidationError

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
