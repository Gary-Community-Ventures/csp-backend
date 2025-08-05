from flask import Response
from json import JSONEncoder, dumps
from datetime import datetime, date, timezone


class CustomJSONEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return (
                obj.astimezone(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


def custom_jsonify(data):
    return Response(dumps(data, cls=CustomJSONEncoder), mimetype="application/json")
