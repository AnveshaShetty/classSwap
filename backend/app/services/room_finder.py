from datetime import date
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.app.models.academic import Room, RoomType, Section, Subject
from backend.app.models.timetable import Timetable
from backend.app.models.substitution import Substitution, SubstitutionStatus, Absence, DateOverride
from backend.app.schemas.substitution import SuitableRoomRecommendation

def find_available_rooms(
    db: Session,
    query_date: date,
    period_no: int,
    section_id: Optional[int] = None,
    is_lab: bool = False,
    allow_lab_for_theory: bool = False,
    exclude_room_id: Optional[int] = None
) -> List[SuitableRoomRecommendation]:
    """
    Find and rank free rooms for a specific date and period.
    Considers room occupancy, section strength, and room type suitability.
    """
    day_of_week = query_date.strftime("%A")

    # 1. Fetch section strength if section_id is provided
    section_strength = 40  # default reasonable fallback
    if section_id:
        section = db.query(Section).filter(Section.id == section_id).first()
        if section:
            section_strength = section.strength

    # 2. Identify occupied rooms in standard timetable for this day & period
    regular_occupied_rooms = {
        row[0] for row in db.query(Timetable.room_id).filter(
            Timetable.day_of_week == day_of_week,
            Timetable.period_no == period_no
        ).all()
    }

    # 3. Identify rooms booked via approved substitutions / date overrides on this date & period
    override_occupied_rooms = {
        row[0] for row in db.query(DateOverride.room_id).filter(
            DateOverride.date == query_date,
            DateOverride.period_no == period_no
        ).all()
    }

    # 4. Rooms booked by pending/accepted substitutions
    sub_occupied_rooms = {
        row[0] for row in db.query(Substitution.room_id).join(Absence).filter(
            Absence.date == query_date,
            Absence.period_no == period_no,
            Substitution.room_id.isnot(None),
            Substitution.status.in_([SubstitutionStatus.ACCEPTED.value, SubstitutionStatus.COMPLETED.value])
        ).all()
    }

    all_occupied_rooms = (regular_occupied_rooms | override_occupied_rooms | sub_occupied_rooms)

    # 5. Retrieve all rooms
    all_rooms = db.query(Room).filter(Room.is_available == True).all()

    suitable_rooms: List[SuitableRoomRecommendation] = []

    for room in all_rooms:
        if room.id == exclude_room_id:
            continue

        is_occupied = room.id in all_occupied_rooms
        if is_occupied:
            continue  # Exclude occupied rooms

        # Room type compatibility check
        # A laboratory should only be assigned when class requires a lab or admin explicitly allows it
        is_room_lab = (room.type == RoomType.LABORATORY.value)
        
        if is_lab and not is_room_lab:
            # Class requires lab, but room is classroom - only as low preference fallback if capacity fits
            type_fit = "Classroom fallback (Lab preferred)"
            type_score = 0.4
        elif not is_lab and is_room_lab and not allow_lab_for_theory:
            # Theory class, room is lab - disallowed unless explicitly allowed
            continue
        elif not is_lab and is_room_lab and allow_lab_for_theory:
            type_fit = "Laboratory assigned for Theory (Admin override)"
            type_score = 0.6
        else:
            type_fit = f"Exact {room.type} Match"
            type_score = 1.0

        # Capacity scoring:
        # Ideal fit: capacity >= section_strength with minimal wasted seats
        has_sufficient_capacity = (room.capacity >= section_strength)
        
        if has_sufficient_capacity:
            wasted_seats = room.capacity - section_strength
            # Score decreases as wasted capacity increases
            capacity_score = max(0.5, 1.0 - (wasted_seats / 100.0))
            cap_note = f"Comfortably fits {section_strength} students ({room.capacity} seats, +{wasted_seats} spare)"
        else:
            deficit = section_strength - room.capacity
            capacity_score = max(0.1, 0.5 - (deficit / 50.0))
            cap_note = f"Warning: Tight capacity ({room.capacity} seats for {section_strength} students)"

        overall_score = (type_score * 0.5) + (capacity_score * 0.5)

        note = f"{type_fit} • {cap_note} • {room.building}"

        suitable_rooms.append(
            SuitableRoomRecommendation(
                room_id=room.id,
                room_name=room.name,
                room_type=room.type,
                capacity=room.capacity,
                section_strength=section_strength,
                building=room.building,
                is_best_fit=False,
                notes=note
            )
        )

    # Sort rooms: sufficient capacity first, then closest capacity fit, then room type
    suitable_rooms.sort(
        key=lambda r: (
            r.capacity >= section_strength,
            (r.room_type == RoomType.LABORATORY.value) if is_lab else (r.room_type == RoomType.CLASSROOM.value),
            -abs(r.capacity - section_strength)
        ),
        reverse=True
    )

    if suitable_rooms:
        suitable_rooms[0].is_best_fit = True

    return suitable_rooms
