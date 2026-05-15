from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
import datetime
from database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # User Info
    name = Column(String)
    email = Column(String, index=True)

    # Preferences
    job_role = Column(String)
    experience_input = Column(String)
    experience_parsed = Column(String)

    expected_salary = Column(String)
    location = Column(String)
    job_type = Column(String)
    work_mode = Column(String)

    # Resume
    resume_path = Column(String)

    # Skills
    all_skills = Column(Text)
    filtered_skills = Column(Text)

    # Queries
    queries = Column(Text)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String)
    company = Column(String)
    location = Column(String)
    link = Column(Text)

    user_email = Column(String, index=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    # ── Email verification ──────────────────────────────────
    is_verified        = Column(Boolean,  default=False,  nullable=False)
    verify_token       = Column(String,   nullable=True)   # UUID token sent in email
    verify_token_expiry= Column(DateTime, nullable=True)   # token valid for 24 h
    # ────────────────────────────────────────────────────────

class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, index=True)
    user_name = Column(String)
    job_title = Column(String)
    company = Column(String)
    job_link = Column(Text)
    status = Column(String, default="pending")
    notes = Column(Text, nullable=True)
    applied_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)