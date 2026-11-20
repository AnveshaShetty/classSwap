import enum
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.database import Base

class AbsenceStatus(str, enum.Enum):
    PENDING = "Pending"
    PROCESSING = "Processing"
    ARRANGED = "Substitution Arranged"
    PARTIAL = "Partially Arranged"
    CANCELLED = "Cancelled"

class SubstitutionStatus(str, enum.Enum):
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    DECLINED = "Declined"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"

class Absence(Base):
    __tablename__ = "absences"

    id = Column(Integer, primary_key=True, index=True)
    faculty_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    period_no = Column(Integer, nullable=False)
    reason = Column(String(255), nullable=True)
    status = Column(String(40), default=AbsenceStatus.PENDING.value, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("faculty_id", "date", "period_no", name="uq_faculty_absence_date_period"),
    )

    # Relationships
    faculty = relationship("User", back_populates="absences")
    substitutions = relationship("Substitution", back_populates="absence", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Absence Fac {self.faculty_id} on {self.date} P{self.period_no} ({self.status})>"

class Substitution(Base):
    __tablename__ = "substitutions"

    id = Column(Integer, primary_key=True, index=True)
    absence_id = Column(Integer, ForeignKey("absences.id", ondelete="CASCADE"), nullable=False)
    timetable_id = Column(Integer, ForeignKey("timetable.id", ondelete="CASCADE"), nullable=False)
    substitute_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(30), default=SubstitutionStatus.PENDING.value, nullable=False)
    
    # Recommendation metric breakdown
    score = Column(Float, default=0.0, nullable=False)
    subject_match_score = Column(Float, default=0.0, nullable=False)
    fairness_score = Column(Float, default=0.0, nullable=False)
    dept_match_score = Column(Float, default=0.0, nullable=False)
    
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    absence = relationship("Absence", back_populates="substitutions")
    timetable_entry = relationship("Timetable", back_populates="substitutions")
    substitute = relationship("User", back_populates="substitutions_received", foreign_keys=[substitute_id])
    room = relationship("Room", back_populates="substitutions")
    date_overrides = relationship("DateOverride", back_populates="substitution", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Substitution Abs {self.absence_id} -> Sub {self.substitute_id} ({self.status})>"

class DateOverride(Base):
    __tablename__ = "date_overrides"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    period_no = Column(Integer, nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    original_faculty_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    substitute_faculty_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    substitution_id = Column(Integer, ForeignKey("substitutions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("date", "period_no", "section_id", name="uq_override_date_period_section"),
    )

    # Relationships
    substitution = relationship("Substitution", back_populates="date_overrides")
    section = relationship("Section")
    subject = relationship("Subject")
    original_faculty = relationship("User", foreign_keys=[original_faculty_id])
    substitute_faculty = relationship("User", foreign_keys=[substitute_faculty_id])
    room = relationship("Room")
