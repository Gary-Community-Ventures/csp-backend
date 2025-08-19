from flask import Blueprint, abort, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import (
    ClerkUserType,
    auth_required,
)
from app.auth.helpers import get_family_user, get_provider_user
from app.extensions import db
from app.models.attendance import Attendance
from app.schemas.attendance import SetAttendanceRequest
from app.sheets.mappings import (
    ChildColumnNames,
    ProviderColumnNames,
    get_child,
    get_children,
    get_family_children,
    get_provider,
    get_providers,
)

bp = Blueprint("attendance", __name__)


@bp.get("/family/attendance")
@auth_required(ClerkUserType.FAMILY)
def family_attendance():
    user = get_family_user()

    child_rows = get_children()

    family_children = get_family_children(user.user_data.family_id, child_rows)

    child_ids = [c.get(ChildColumnNames.ID) for c in family_children]

    attendance_data: list[Attendance] = Attendance.filter_by_child_ids(child_ids).all()

    if len(attendance_data) == 0:
        return jsonify({"attendance": [], "children": [], "providers": []})

    provider_rows = get_providers()
    attendance: list[dict] = []
    children: list[dict] = []
    providers: list[dict] = []

    for att_data in attendance_data:
        att_data.record_family_opened()
        db.session.add(att_data)

        child = get_child(att_data.child_google_sheet_id, family_children)

        if child is None:
            # child is not in the family anymore, so mark them as 0 hours
            att_data.set_family_entered(0)
            continue

        child_included = False
        for response_child in children:
            if response_child["id"] == child.get(ChildColumnNames.ID):
                child_included = True
                break

        if not child_included:
            children.append(
                {
                    "id": child.get(ChildColumnNames.ID),
                    "first_name": child.get(ChildColumnNames.FIRST_NAME),
                    "last_name": child.get(ChildColumnNames.LAST_NAME),
                }
            )

        provider = get_provider(att_data.provider_google_sheet_id, provider_rows)

        if provider is None:
            # The provider has been deleted
            att_data.set_family_entered(0)
            continue

        provider_included = False
        for response_provider in providers:
            if response_provider["id"] == provider.get(ProviderColumnNames.ID):
                provider_included = True
                break

        if not provider_included:
            providers.append(
                {
                    "id": provider.get(ProviderColumnNames.ID),
                    "name": provider.get(ProviderColumnNames.NAME),
                }
            )

        attendance.append(
            {
                "id": att_data.id,
                "date": att_data.week.isoformat(),
                "child_id": child.get(ChildColumnNames.ID),
                "provider_id": provider.get(ProviderColumnNames.ID),
            }
        )

    db.session.commit()

    return jsonify(
        {
            "attendance": attendance,
            "children": children,
            "providers": providers,
        }
    )


def find_attendance(attendance_id: str, attendance_data: list[Attendance]):
    for attendance in attendance_data:
        if str(attendance.id) == attendance_id:
            return attendance

    abort(404, description=f"Attendance with ID {attendance_id} not found.")


@bp.post("/family/attendance")
@auth_required(ClerkUserType.FAMILY)
def enter_family_attendance():
    try:
        data = SetAttendanceRequest(**request.json)
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    user = get_family_user()

    child_rows = get_children()
    family_children = get_family_children(user.user_data.family_id, child_rows)
    child_ids = [c.get(ChildColumnNames.ID) for c in family_children]

    ids = [att.id for att in data.attendance]

    attendance_data: list[Attendance] = Attendance.filter_by_child_ids(child_ids).filter(Attendance.id.in_(ids)).all()

    for family_entered in data.attendance:
        attendance = find_attendance(family_entered.id, attendance_data)
        attendance.set_family_entered(family_entered.hours)
        db.session.add(attendance)

    db.session.commit()

    return jsonify({"message": "Success"}, 200)


@bp.get("/provider/attendance")
@auth_required(ClerkUserType.PROVIDER)
def provider_attendance():
    user = get_provider_user()

    attendance_data: list[Attendance] = Attendance.filter_by_provider_id(user.user_data.provider_id).all()

    if len(attendance_data) == 0:
        return jsonify({"attendance": [], "children": []})

    child_rows = get_children()

    attendance: list[dict] = []
    children: list[dict] = []

    for att_data in attendance_data:
        att_data.record_provider_opened()
        db.session.add(att_data)

        child = get_child(att_data.child_google_sheet_id, child_rows)

        if child is None:
            # the child has been deleted
            att_data.set_provider_entered(0)
            continue

        child_included = False
        for response_child in children:
            if response_child["id"] == child.get(ChildColumnNames.ID):
                child_included = True
                break

        if not child_included:
            children.append(
                {
                    "id": child.get(ChildColumnNames.ID),
                    "first_name": child.get(ChildColumnNames.FIRST_NAME),
                    "last_name": child.get(ChildColumnNames.LAST_NAME),
                }
            )

        attendance.append(
            {
                "id": att_data.id,
                "date": att_data.week.isoformat(),
                "child_id": child.get(ChildColumnNames.ID),
            }
        )

    db.session.commit()

    return jsonify(
        {
            "attendance": attendance,
            "children": children,
        }
    )


@bp.post("/provider/attendance")
@auth_required(ClerkUserType.PROVIDER)
def attendance_provider():
    try:
        data = SetAttendanceRequest(**request.json)
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    user = get_provider_user()

    ids = [att.id for att in data.attendance]

    attendance_data: list[Attendance] = (
        Attendance.filter_by_provider_id(user.user_data.provider_id).filter(Attendance.id.in_(ids)).all()
    )

    for provider_entered in data.attendance:
        attendance = find_attendance(provider_entered.id, attendance_data)
        attendance.set_provider_entered(provider_entered.hours)
        db.session.add(attendance)

    db.session.commit()

    return jsonify({"message": "Success"}, 200)
