from pydantic import BaseModel, Field
from datetime import date, datetime

class ChildBase(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date

class ChildCreate(ChildBase):
    family_id: int

from typing import Optional

class ChildResponse(ChildBase):
    id: int
    family_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
