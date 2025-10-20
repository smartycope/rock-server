from flask import Blueprint, send_file

bp = Blueprint("customized_form", __name__)

@bp.route("/")
def form():
    return send_file('static/customized-form.html')

@bp.route("/assets/<path:path>")
def assets(path):
    return send_file(f'static/assets/{path}')
