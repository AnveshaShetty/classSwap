from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminChainEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: str = Field(min_length=1, max_length=80)
    email: EmailStr


class AdminChainUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department: str = Field(min_length=1, max_length=120)
    entries: list[AdminChainEntry]


class AdminChainEntryRead(AdminChainEntry):
    name: str
    role: str


class AdminChainRead(BaseModel):
    department: str
    entries: list[AdminChainEntryRead]


class ActingAdminRead(BaseModel):
    name: str
    email: EmailStr
    role: str
    department: str
    position: str


class LeaveCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    reason: str = Field(default="Whole-day leave", min_length=1, max_length=255)


class LeaveRead(BaseModel):
    user_id: int
    date: date
    absences_created: int = 0
