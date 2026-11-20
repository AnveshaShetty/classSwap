import enum
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.database import Base

class RoomType(str, enum.Enum):
    CLASSROOM = "Classroom"
    LABORATORY = "Laboratory"

class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False)
    department = Column(String(120), nullable=False)
    is_lab = Column(Boolean, default=False, nullable=False)
    credits = Column(Integer, default=3, nullable=False)

    # Relationships
    faculty_qualifications = relationship("FacultySubject", back_populates="subject", cascade="all, delete-orphan")
    timetable_entries = relationship("Timetable", back_populates="subject")

    def __repr__(self):
        return f"<Subject {self.code} - {self.name}>"

class FacultySubject(Base):
    __tablename__ = "faculty_subjects"

    id = Column(Integer, primary_key=True, index=True)
    faculty_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    experience_years = Column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("faculty_id", "subject_id", name="uq_faculty_subject"),
    )

    # Relationships
    faculty = relationship("User", back_populates="faculty_subjects")
    subject = relationship("Subject", back_populates="faculty_qualifications")

class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(60), unique=True, index=True, nullable=False)
    type = Column(String(30), default=RoomType.CLASSROOM.value, nullable=False)
    capacity = Column(Integer, nullable=False)
    building = Column(String(100), default="Main Academic Block", nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)

    # Relationships
    timetable_entries = relationship("Timetable", back_populates="room")
    substitutions = relationship("Substitution", back_populates="room")

    def __repr__(self):
        return f"<Room {self.name} ({self.type}, Cap: {self.capacity})>"

class Section(Base):
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(60), unique=True, index=True, nullable=False)
    semester = Column(Integer, nullable=False)
    strength = Column(Integer, nullable=False)
    department = Column(String(120), nullable=False)

    # Relationships
    timetable_entries = relationship("Timetable", back_populates="section")

    def __repr__(self):
        return f"<Section {self.name} (Strength: {self.strength})>"
