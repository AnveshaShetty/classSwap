from pydantic import BaseModel, ConfigDict
from typing import Optional, List

class PeriodConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period_no: int
    label: str
    start_time: str
    end_time: str
    duration_minutes: int

class TimetableCreate(BaseModel):
    section_id: int
    subject_id: int
    faculty_id: int
    room_id: int
    day_of_week: str
    period_no: int

class TimetableUpdate(BaseModel):
    section_id: Optional[int] = None
    subject_id: Optional[int] = None
    faculty_id: Optional[int] = None
    room_id: Optional[int] = None
    day_of_week: Optional[str] = None
    period_no: Optional[int] = None

class TimetableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    section_id: int
    subject_id: int
    faculty_id: int
    room_id: int
    day_of_week: str
    period_no: int
    
    # Nested display info
    section_name: Optional[str] = None
    subject_name: Optional[str] = None
    subject_code: Optional[str] = None
    faculty_name: Optional[str] = None
    room_name: Optional[str] = None

class TimetableUploadPreviewItem(BaseModel):
    section_name: str
    subject_name: str
    faculty_email: str
    room_name: str
    day_of_week: str
    period_no: int
    is_valid: bool = True
    errors: List[str] = []

class TimetableUploadResponse(BaseModel):
    total_rows: int
    valid_rows: int
    error_rows: int
    preview: List[TimetableUploadPreviewItem]
    message: str
