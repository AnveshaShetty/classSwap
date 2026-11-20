from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.database import Base

class PeriodConfig(Base):
    __tablename__ = "period_configs"

    period_no = Column(Integer, primary_key=True)
    label = Column(String(50), nullable=False)
    start_time = Column(String(20), nullable=False)
    end_time = Column(String(20), nullable=False)
    duration_minutes = Column(Integer, default=50, nullable=False)

    def __repr__(self):
        return f"<Period {self.period_no}: {self.start_time} - {self.end_time}>"

class Timetable(Base):
    __tablename__ = "timetable"

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    faculty_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(String(20), nullable=False)  # Monday, Tuesday, Wednesday, Thursday, Friday, Saturday
    period_no = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("faculty_id", "day_of_week", "period_no", name="uq_faculty_time_slot"),
        UniqueConstraint("room_id", "day_of_week", "period_no", name="uq_room_time_slot"),
        UniqueConstraint("section_id", "day_of_week", "period_no", name="uq_section_time_slot"),
    )

    # Relationships
    section = relationship("Section", back_populates="timetable_entries")
    subject = relationship("Subject", back_populates="timetable_entries")
    faculty = relationship("User", back_populates="timetable_entries")
    room = relationship("Room", back_populates="timetable_entries")
    substitutions = relationship("Substitution", back_populates="timetable_entry")

    def __repr__(self):
        return f"<Timetable {self.day_of_week} P{self.period_no}: Sec {self.section_id}, Sub {self.subject_id}, Fac {self.faculty_id}>"
