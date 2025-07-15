from flask import Blueprint, jsonify, request

bp = Blueprint("family", __name__)


# TODO: add api key
@bp.post("/family")
def new_family():
    data = request.json

    # TODO: create family in db

    # send clerk invite

    return jsonify(data)
