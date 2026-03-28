"""Database models."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Text, Enum as SQLEnum, Numeric, CHAR
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class GUID(TypeDecorator):
    """Platform-independent GUID type (uses PostgreSQL UUID, otherwise stores as CHAR(36))."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(uuid.UUID(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


class UserRole(str, enum.Enum):
    KID = "kid"
    PARENT = "parent"
    ADMIN = "admin"


class TaskCategory(str, enum.Enum):
    DISCIPLINARY = "disciplinary"
    PHYSICAL = "physical"
    SPIRITUAL = "spiritual"
    EDUCATIONAL = "educational"
    HOUSEHOLD = "household"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RedemptionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class LeaderboardScope(str, enum.Enum):
    GLOBAL = "global"
    FAMILY = "family"


class LeaderboardPeriod(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ALL_TIME = "all_time"


class PvpMatchStatus(str, enum.Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    COMPLETED = "completed"


class User(Base):
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.KID)
    avatar_url = Column(String(500), nullable=True)
    parent_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    points_balance = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    children = relationship("User", backref="parent", remote_side=[id])
    tasks_assigned = relationship("Task", back_populates="assigned_user", foreign_keys="Task.assigned_to")
    tasks_created = relationship("Task", back_populates="creator", foreign_keys="Task.created_by")
    tasks_approved = relationship("Task", back_populates="approver", foreign_keys="Task.approved_by")
    redemptions = relationship("Redemption", back_populates="user", foreign_keys="Redemption.user_id")
    game_sessions = relationship("GameSession", back_populates="user")
    leaderboard_entries = relationship("LeaderboardEntry", back_populates="user")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    user = relationship("User", back_populates="refresh_tokens")


class AdminAccount(Base):
    __tablename__ = "admin_accounts"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    avatar_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskCategory(Base):
    __tablename__ = "task_categories"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False)
    icon = Column(String(10), nullable=True)
    color_code = Column(String(7), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    tasks = relationship("Task", back_populates="category")
    templates = relationship("TaskTemplate", back_populates="category")


class TaskTemplate(Base):
    __tablename__ = "task_templates"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category_id = Column(GUID(), ForeignKey("task_categories.id"), nullable=True)
    suggested_points = Column(Integer, default=10)
    age_min = Column(Integer, default=0)
    age_max = Column(Integer, default=18)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    category = relationship("TaskCategory", back_populates="templates")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category_id = Column(GUID(), ForeignKey("task_categories.id"), nullable=True)
    assigned_to = Column(GUID(), ForeignKey("users.id"), nullable=False)
    created_by = Column(GUID(), ForeignKey("users.id"), nullable=False)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    priority = Column(SQLEnum(TaskPriority), default=TaskPriority.MEDIUM)
    points = Column(Integer, default=10)
    due_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    approved_by = Column(GUID(), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    category = relationship("TaskCategory", back_populates="tasks")
    assigned_user = relationship("User", back_populates="tasks_assigned", foreign_keys=[assigned_to])
    creator = relationship("User", back_populates="tasks_created", foreign_keys=[created_by])
    approver = relationship("User", back_populates="tasks_approved", foreign_keys=[approved_by])


class Reward(Base):
    __tablename__ = "rewards"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    points_required = Column(Integer, nullable=False)
    icon = Column(String(10), nullable=True)
    image_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    redemptions = relationship("Redemption", back_populates="reward")


class Redemption(Base):
    __tablename__ = "redemptions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    reward_id = Column(GUID(), ForeignKey("rewards.id"), nullable=False)
    status = Column(SQLEnum(RedemptionStatus), default=RedemptionStatus.PENDING)
    requested_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    processed_by = Column(GUID(), ForeignKey("users.id"), nullable=True)

    # Relationships
    user = relationship("User", back_populates="redemptions", foreign_keys=[user_id])
    reward = relationship("Reward", back_populates="redemptions")


class GameType(Base):
    __tablename__ = "game_types"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    points_reward_base = Column(Integer, default=10)
    icon = Column(String(10), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    sessions = relationship("GameSession", back_populates="game_type")


class GameSession(Base):
    __tablename__ = "game_sessions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    game_type_id = Column(GUID(), ForeignKey("game_types.id"), nullable=False)
    score = Column(Integer, default=0)
    points_earned = Column(Integer, default=0)
    difficulty = Column(String(20), default="medium")
    duration_seconds = Column(Integer, default=0)
    completed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="game_sessions")
    game_type = relationship("GameType", back_populates="sessions")


class LeaderboardEntry(Base):
    __tablename__ = "leaderboard_entries"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    period = Column(SQLEnum(LeaderboardPeriod), default=LeaderboardPeriod.WEEKLY)
    scope = Column(SQLEnum(LeaderboardScope), default=LeaderboardScope.GLOBAL)
    total_points = Column(Integer, default=0)
    tasks_completed = Column(Integer, default=0)
    games_played = Column(Integer, default=0)
    rank = Column(Integer, nullable=True)
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    user = relationship("User", back_populates="leaderboard_entries")


class PvpMatch(Base):
    __tablename__ = "pvp_matches"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    player_white_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    player_black_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    winner_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    status = Column(SQLEnum(PvpMatchStatus), default=PvpMatchStatus.WAITING)
    invite_code = Column(String(8), nullable=True, unique=True)
    moves_pgn = Column(Text, nullable=True)
    time_control_seconds = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
