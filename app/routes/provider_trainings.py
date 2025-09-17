from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import ClerkUserType, auth_required
from app.auth.helpers import get_provider_user
from app.schemas.provider_training import (
    ProviderTrainingResponse,
    ProviderTrainingUpdateRequest,
)
from app.supabase.helpers import cols, unwrap_or_abort
from app.supabase.tables import Provider

bp = Blueprint("provider_trainings", __name__, url_prefix="/provider")


@bp.get("/trainings")
@auth_required(ClerkUserType.PROVIDER)
def get_trainings():
    """
    Get the training completion status for the authenticated provider.
    """
    user = get_provider_user()
    provider_id = user.user_data.provider_id

    all_training_columns = [
        Provider.CPR_ONLINE_TRAINING_COMPLETED_AT,
        Provider.CHILD_SAFETY_MODULE_TRAINING_COMPLETED_AT,
        Provider.SAFE_SLEEP_FOR_INFANTS_TRAINING_COMPLETED_AT,
        Provider.HOME_SAFETY_AND_INJURY_PREVENTION_TRAINING_COMPLETED_AT,
    ]

    provider_result = Provider.select_by_id(
        cols(*all_training_columns),
        int(provider_id),
    ).execute()

    provider_data = unwrap_or_abort(provider_result)

    response_data = {field.name: field(provider_data) for field in all_training_columns}

    return (
        ProviderTrainingResponse(**response_data).model_dump_json(by_alias=True),
        200,
        {"Content-Type": "application/json"},
    )


@bp.patch("/trainings")
@auth_required(ClerkUserType.PROVIDER)
def update_trainings():
    """
    Update the training completion status for the authenticated provider.
    """
    user = get_provider_user()
    provider_id = user.user_data.provider_id

    try:
        update_data = ProviderTrainingUpdateRequest.model_validate(request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    data_to_update = {}
    now = datetime.now(timezone.utc).isoformat()

    update_fields = update_data.model_dump(exclude_unset=True)

    if not update_fields:
        return jsonify({"error": "No updatable fields provided"}), 400

    for field_name, value in update_fields.items():
        if value is not None:
            data_to_update[field_name] = now if value else None


    updated_provider_result = (
        current_app.supabase_client.table(Provider.TABLE_NAME)
        .update(data_to_update)
        .eq(Provider.ID, int(provider_id))
        .execute()
    )

    updated_provider_data = unwrap_or_abort(updated_provider_result)

    if not updated_provider_data:
        return jsonify({"error": "Failed to update provider trainings"}), 500

    all_training_columns = [
        Provider.CPR_ONLINE_TRAINING_COMPLETED_AT,
        Provider.CHILD_SAFETY_MODULE_TRAINING_COMPLETED_AT,
        Provider.SAFE_SLEEP_FOR_INFANTS_TRAINING_COMPLETED_AT,
        Provider.HOME_SAFETY_AND_INJURY_PREVENTION_TRAINING_COMPLETED_AT,
    ]

    response_data = {field.name: field(updated_provider_data[0]) for field in all_training_columns}

    return (
        ProviderTrainingResponse(**response_data).model_dump_json(by_alias=True),
        200,
        {"Content-Type": "application/json"},
    )
