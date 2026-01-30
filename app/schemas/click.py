from typing import Optional

from pydantic import BaseModel, Field


class ClickBase(BaseModel):
    tracking_id: str = Field(..., max_length=128)


class ClickCreate(ClickBase):
    url: Optional[str] = Field(None, max_length=2048)


class ClickGetQuery(ClickBase):
    pass


class ClickResponse(ClickBase):

    model_config = {"from_attributes": True}
