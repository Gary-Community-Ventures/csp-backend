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
from app.supabase.helpers import cols, unwrap_or_abort
from app.supabase.tables import Child, Provider

bp = Blueprint("attendance", __name__)


@bp.get("/family/attendance")
@auth_required(ClerkUserType.FAMILY)
def family_attendance():
    user = get_family_user()

    children_result = Child.select_by_family_id(
        cols(
            Child.ID,
            Child.FIRST_NAME,
            Child.LAST_NAME,
            Provider.join(Provider.ID, Provider.NAME),
        ),
        int(user.user_data.family_id),
    ).execute()
    child_data = unwrap_or_abort(children_result)

    child_ids = [Child.ID(c) for c in child_data]

    attendance_data: list[Attendance] = Attendance.filter_by_child_ids(child_ids).all()

    if len(attendance_data) == 0:
        return jsonify({"attendance": [], "children": [], "providers": []})

    attendance: list[dict] = []
    children: dict = {}
    providers: dict = {}

    for att_data in attendance_data:
        att_data.record_family_opened()
        db.session.add(att_data)

        child = None
        for c in child_data:
            if Child.ID(c) == att_data.child_google_sheet_id:
                child = c
                break

        if child is None:
            # child is not in the family anymore, so mark them as 0 hours
            att_data.set_family_entered(0)
            continue

        if Child.ID(child) not in children:
            children[Child.ID(child)] = {
                "id": Child.ID(child),
                "first_name": Child.FIRST_NAME(child),
                "last_name": Child.LAST_NAME(child),
            }

        provider = None
        for provider in Provider.unwrap(child):
            if Provider.ID(provider) == att_data.provider_google_sheet_id:
                provider = provider
                break

        if provider is None:
            # The provider has been deleted
            att_data.set_family_entered(0)
            continue

        if Provider.ID(provider) not in providers:
            providers[Provider.ID(provider)] = {
                "id": Provider.ID(provider),
                "name": Provider.NAME(provider),
            }

        attendance.append(
            {
                "id": att_data.id,
                "date": att_data.week.isoformat(),
                "child_id": Child.ID(child),
                "provider_id": Provider.ID(provider),
            }
        )

    children = list(children.values())
    providers = list(providers.values())

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

    children_result = Child.select_by_family_id(cols(Child.ID), int(user.user_data.family_id)).execute()
    children = unwrap_or_abort(children_result)
    child_ids = [Child.ID(c) for c in children]

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

    children_result = Child.select_by_family_id(
        cols(Child.ID, Child.FIRST_NAME, Child.LAST_NAME), int(user.user_data.family_id)
    ).execute()
    child_data = unwrap_or_abort(children_result)

    attendance: list[dict] = []
    children: dict = {}

    for att_data in attendance_data:
        att_data.record_provider_opened()
        db.session.add(att_data)

        child = None
        for family_child in child_data:
            if Child.ID(family_child) == att_data.child_google_sheet_id:
                child = family_child
                break

        if child is None:
            # the child has been deleted
            att_data.set_provider_entered(0)
            continue

        if Child.ID(child) not in children:
            children[Child.ID(child)] = {
                "id": Child.ID(child),
                "first_name": Child.FIRST_NAME(child),
                "last_name": Child.LAST_NAME(child),
            }

        attendance.append(
            {
                "id": att_data.id,
                "date": att_data.week.isoformat(),
                "child_id": Child.ID(child),
            }
        )

    children = list(children.values())

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
