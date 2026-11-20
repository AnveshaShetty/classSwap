from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import date, datetime

class AbsenceCreate(BaseModel):
    date: date
    period_nos: List[int]
    reason: Optional[str] = None
    faculty_id: Optional[int] = None  # Admin can specify, or defaults to current faculty user

class AbsenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    faculty_id: int
    faculty_name: Optional[str] = None
    date: date
    period_no: int
    reason: Optional[str] = None
    status: str
    created_at: datetime
    
    # Associated scheduled class info
    timetable_id: Optional[int] = None
    subject_name: Optional[str] = None
    section_name: Optional[str] = None
    room_name: Optional[str] = None

class CandidateRecommendation(BaseModel):
    faculty_id: int
    faculty_name: str
    email: str
    department: str
    monthly_substitutions: int
    subject_match: float
    fairness_score: float
    dept_match: float
    final_score: float
    relevance_details: str
    is_top_choice: bool = False

class SuitableRoomRecommendation(BaseModel):
    room_id: int
    room_name: str
    room_type: str
    capacity: int
    section_strength: int
    building: str
    is_best_fit: bool = False
    notes: str

class RecommendationResponse(BaseModel):
    absence_id: int
    timetable_id: int
    date: date
    period_no: int
    subject_name: str
    subject_code: str
    is_lab: bool
    section_name: str
    section_strength: int
    current_room_name: str
    candidates: List[CandidateRecommendation]
    suitable_rooms: List[SuitableRoomRecommendation]

class SubstitutionRequestCreate(BaseModel):
    absence_id: int
    substitute_id: int
    room_id: Optional[int] = None
    notes: Optional[str] = None

class SubstitutionAction(BaseModel):
    substitution_id: int
    action: str  # "accept" or "decline"
    notes: Optional[str] = None

class SubstitutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    absence_id: int
    timetable_id: int
    substitute_id: int
    substitute_name: Optional[str] = None
    substitute_email: Optional[str] = None
    absent_faculty_name: Optional[str] = None
    subject_name: Optional[str] = None
    section_name: Optional[str] = None
    date: date
    period_no: int
    room_id: Optional[int] = None
    room_name: Optional[str] = None
    status: str
    score: float
    subject_match_score: float
    fairness_score: float
    dept_match_score: float
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
