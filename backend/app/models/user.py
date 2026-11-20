import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.orm import relationship
from backend.app.database import Base

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    FACULTY = "faculty"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default=UserRole.FACULTY.value, nullable=False)
    department = Column(String(120), nullable=False)
    phone = Column(String(30), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    faculty_subjects = relationship("FacultySubject", back_populates="faculty", cascade="all, delete-orphan")
    timetable_entries = relationship("Timetable", back_populates="faculty")
    absences = relationship("Absence", back_populates="faculty")
    substitutions_received = relationship("Substitution", back_populates="substitute", foreign_keys="Substitution.substitute_id")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"
