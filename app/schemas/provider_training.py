from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProviderTrainingResponse(BaseModel):
    cpr_certified: Optional[bool] = Field(None)
    cpr_training_link: Optional[str] = Field(None)
    cpr_online_training_completed_at: Optional[datetime] = Field(None)
    pdis_first_aid_cpr_completed_at: Optional[datetime] = Field(None)
    pdis_standard_precautions_completed_at: Optional[datetime] = Field(None)
    pdis_preventing_child_abuse_completed_at: Optional[datetime] = Field(None)
    pdis_infant_safe_sleep_completed_at: Optional[datetime] = Field(None)
    pdis_emergency_preparedness_completed_at: Optional[datetime] = Field(None)
    pdis_injury_prevention_completed_at: Optional[datetime] = Field(None)
    pdis_preventing_shaken_baby_completed_at: Optional[datetime] = Field(None)
    pdis_recognizing_impact_of_bias_completed_at: Optional[datetime] = Field(None)
    pdis_medication_administration_part_one_completed_at: Optional[datetime] = Field(None)

    class Config:
        populate_by_name = True
