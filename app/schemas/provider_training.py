from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProviderTrainingResponse(BaseModel):
    cpr_online_training_completed_at: Optional[datetime] = Field(None)
    child_safety_module_training_completed_at: Optional[datetime] = Field(None)
    safe_sleep_for_infants_training_completed_at: Optional[datetime] = Field(None)
    home_safety_and_injury_prevention_training_completed_at: Optional[datetime] = Field(None)
    cpr_certified: Optional[bool] = Field(None)
    cpr_training_link: Optional[str] = Field(None)

    class Config:
        populate_by_name = True
