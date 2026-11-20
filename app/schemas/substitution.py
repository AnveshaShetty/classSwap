from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SubstitutionCreate(BaseModel):
    absence_id: int
    substitute_id: int


class SubstitutionRespond(BaseModel):
    status: Literal["accepted", "declined"]


class SubstitutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    absence_id: int
    substitute_id: int
    room_id: int
    date: date
    period_no: int
    status: str
    created_at: datetime
    responded_at: datetime | None


class SubstitutionActionRead(BaseModel):
    substitution: SubstitutionRead
    next_request: SubstitutionRead | None


class InboxItemRead(BaseModel):
    substitution: SubstitutionRead
    absent_faculty: str
    subject: str
    section: str


class FreeRoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    capacity: int
