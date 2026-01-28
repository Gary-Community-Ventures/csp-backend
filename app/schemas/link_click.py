from pydantic import BaseModel, Field


class LinkClickBase(BaseModel):
    link: str = Field(..., max_length=2048)


class LinkClickCreate(LinkClickBase):
    pass

class LinkClickGetArgs(LinkClickBase):
    pass


class LinkClickResponse(LinkClickBase):
    
    model_config = {"from_attributes": True}
