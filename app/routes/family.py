from flask import Blueprint, jsonify, request
from sqlalchemy import select
from app.models import Household
from app.extensions import db

bp = Blueprint("family", __name__)

# TODO: add api key
@bp.post("/family")
def new_family():
    data = request.json

    print(db.session.execute(select(Household)).scalars())

    # create family in db
    household = Household()
    db.session.add(household)
    db.session.commit()

    # send clerk invite

    return jsonify(data)
