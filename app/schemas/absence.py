from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AbsenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    periods: list[int] = Field(min_length=1, max_length=7)
    reason: str = Field(min_length=1, max_length=255)

    @field_validator("periods")
    @classmethod
    def validate_periods(cls, periods: list[int]) -> list[int]:
        if len(set(periods)) != len(periods):
            raise ValueError("Periods must not be repeated.")
        if any(period < 1 or period > 7 for period in periods):
            raise ValueError("Periods must be between 1 and 7.")
        return sorted(periods)


class AbsenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timetable_id: int
    faculty_id: int
    date: date
    period_no: int
    reason: str
