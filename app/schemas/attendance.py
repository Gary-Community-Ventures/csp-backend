from pydantic import BaseModel


class AttendanceData(BaseModel):
    id: str
    hours: int


class SetAttendanceRequest(BaseModel):
    attendance: list[AttendanceData]
