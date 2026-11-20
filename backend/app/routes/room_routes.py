from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from backend.app.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.models.academic import Room, RoomType, Section
from backend.app.schemas.academic import RoomResponse
from backend.app.schemas.substitution import SuitableRoomRecommendation
from backend.app.services.room_finder import find_available_rooms

router = APIRouter(prefix="/api/rooms", tags=["Rooms & Availability"])

@router.get("", response_model=List[RoomResponse])
def list_rooms(db: Session = Depends(get_db)):
    """List all registered classrooms and laboratories."""
    rooms = db.query(Room).order_by(Room.name).all()
    return rooms

@router.get("/free", response_model=List[SuitableRoomRecommendation])
def get_free_rooms(
    target_date: date = Query(..., description="Date for room inquiry"),
    period_no: int = Query(..., ge=1, le=8, description="Period number"),
    section_id: Optional[int] = Query(None, description="Section ID for capacity and strength matching"),
    is_lab: bool = Query(False, description="Whether the class requires laboratory equipment"),
    allow_lab_for_theory: bool = Query(False, description="Allow assigning a lab for theory classes"),
    db: Session = Depends(get_db)
):
    """
    Classroom Availability Engine:
    Identifies all free rooms for the chosen date and period,
    excluding already booked rooms, matching capacity with section strength,
    and scoring suitable classrooms and laboratories.
    """
    recommendations = find_available_rooms(
        db=db,
        query_date=target_date,
        period_no=period_no,
        section_id=section_id,
        is_lab=is_lab,
        allow_lab_for_theory=allow_lab_for_theory
    )
    return recommendations
