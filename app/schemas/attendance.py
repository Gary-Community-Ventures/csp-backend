from pydantic import BaseModel


class AttendanceData(BaseModel):
    id: str
    full_days: int
    half_days: int


class SetAttendanceRequest(BaseModel):
    attendance: list[AttendanceData]
