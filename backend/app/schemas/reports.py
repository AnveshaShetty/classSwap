from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import date

class FacultyWorkloadItem(BaseModel):
    faculty_id: int
    faculty_name: str
    department: str
    substitutions_completed: int
    hours_covered: float
    last_substitution_date: Optional[str] = None

class DepartmentStatItem(BaseModel):
    department: str
    total_absences: int
    substitutions_completed: int
    hours_recovered: float
    recovery_rate_pct: float

class SubjectSubstitutedItem(BaseModel):
    subject_code: str
    subject_name: str
    department: str
    substitutions_count: int

class MonthlyReportResponse(BaseModel):
    month: int
    year: int
    month_name: str
    total_absences: int
    substitutions_requested: int
    substitutions_accepted: int
    substitutions_declined: int
    classes_recovered: int
    idle_hours_saved: float
    recovery_rate_pct: float
    faculty_workload: List[FacultyWorkloadItem]
    department_stats: List[DepartmentStatItem]
    top_substituted_subjects: List[SubjectSubstitutedItem]
