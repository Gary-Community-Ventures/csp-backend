from flask import Blueprint

from app.auth.decorators import ClerkUserType, auth_required
from app.auth.helpers import get_provider_user
from app.schemas.provider_training import (
    ProviderTrainingResponse,
)
from app.supabase.helpers import cols, unwrap_or_abort
from app.supabase.tables import Provider

bp = Blueprint("provider_trainings", __name__, url_prefix="/provider")

ALL_TRAINING_COLUMNS = [
    Provider.CPR_ONLINE_TRAINING_COMPLETED_AT,
    Provider.PDIS_FIRST_AID_CPR_COMPLETED_AT,
    Provider.PDIS_STANDARD_PRECAUTIONS_COMPLETED_AT,
    Provider.PDIS_PREVENTING_CHILD_ABUSE_COMPLETED_AT,
    Provider.PDIS_INFANT_SAFE_SLEEP_COMPLETED_AT,
    Provider.PDIS_EMERGENCY_PREPAREDNESS_COMPLETED_AT,
    Provider.PDIS_INJURY_PREVENTION_COMPLETED_AT,
    Provider.PDIS_PREVENTING_SHAKEN_BABY_COMPLETED_AT,
    Provider.PDIS_RECOGNIZING_IMPACT_OF_BIAS_COMPLETED_AT,
    Provider.PDIS_MEDICATION_ADMINISTRATION_PART_ONE_COMPLETED_AT,
]

ALL_TRAINING_COLUMNS_WITH_CPR = ALL_TRAINING_COLUMNS + [
    Provider.CPR_CERTIFIED,
    Provider.CPR_TRAINING_LINK,
]


@bp.get("/trainings")
@auth_required(ClerkUserType.PROVIDER)
def get_trainings():
    """
    Get the training completion status for the authenticated provider.
    """
    user = get_provider_user()
    provider_id = user.user_data.provider_id

    provider_result = Provider.select_by_id(
        cols(*ALL_TRAINING_COLUMNS_WITH_CPR),
        int(provider_id),
    ).execute()

    provider_data = unwrap_or_abort(provider_result)

    response_data = {field.name: field(provider_data) for field in ALL_TRAINING_COLUMNS}

    # Add CPR fields with appropriate transformation
    cpr_certified = None
    if Provider.CPR_CERTIFIED(provider_data) is not None:
        cpr_certified = Provider.CPR_CERTIFIED(provider_data).lower() == "yes"

    response_data["cpr_certified"] = cpr_certified
    response_data["cpr_training_link"] = Provider.CPR_TRAINING_LINK(provider_data)

    return (
        ProviderTrainingResponse(**response_data).model_dump_json(by_alias=True),
        200,
        {"Content-Type": "application/json"},
    )
