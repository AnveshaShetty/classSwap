from pydantic import BaseModel, ConfigDict
from typing import Optional, List

class SubjectBase(BaseModel):
    code: str
    name: str
    department: str
    is_lab: bool = False
    credits: int = 3

class SubjectCreate(SubjectBase):
    pass

class SubjectResponse(SubjectBase):
    model_config = ConfigDict(from_attributes=True)
    id: int

class RoomBase(BaseModel):
    name: str
    type: str = "Classroom"
    capacity: int
    building: str = "Main Academic Block"
    is_available: bool = True

class RoomCreate(RoomBase):
    pass

class RoomResponse(RoomBase):
    model_config = ConfigDict(from_attributes=True)
    id: int

class SectionBase(BaseModel):
    name: str
    semester: int
    strength: int
    department: str

class SectionCreate(SectionBase):
    pass

class SectionResponse(SectionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int

class FacultySubjectAssign(BaseModel):
    faculty_id: int
    subject_id: int
    experience_years: int = 1
