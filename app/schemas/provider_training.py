from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProviderTrainingResponse(BaseModel):
    cpr_online_training_completed_at: Optional[datetime] = Field(None, alias="cpr_online_training_completed_at")
    child_safety_module_training_completed_at: Optional[datetime] = Field(
        None, alias="child_safety_module_training_completed_at"
    )
    safe_sleep_for_infants_training_completed_at: Optional[datetime] = Field(
        None, alias="safe_sleep_for_infants_training_completed_at"
    )
    home_safety_and_injury_prevention_training_completed_at: Optional[datetime] = Field(
        None, alias="home_safety_and_injury_prevention_training_completed_at"
    )

    class Config:
        populate_by_name = True


class ProviderTrainingUpdateRequest(BaseModel):
    child_safety_module_training_completed_at: Optional[bool] = None
    safe_sleep_for_infants_training_completed_at: Optional[bool] = None
    home_safety_and_injury_prevention_training_completed_at: Optional[bool] = None
