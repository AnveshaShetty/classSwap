from pydantic import BaseModel, ConfigDict, EmailStr


class SuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    faculty_id: int
    name: str
    email: EmailStr
    score: float
    reason: str
