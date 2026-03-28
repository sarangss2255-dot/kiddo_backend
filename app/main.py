"""Main FastAPI application."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import admin, admin_auth, auth, games, leaderboard, rewards, tasks, users
from app.config import settings
from app.core.firebase_auth import initialize_firebase_admin, is_firebase_admin_initialized
from app.database import engine, Base

# Create database tables
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(
    title="Kiddo App API",
    description="Backend API for Kids Task Management App",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(rewards.router, prefix="/api/v1")
app.include_router(games.router, prefix="/api/v1")
app.include_router(leaderboard.router, prefix="/api/v1")
app.include_router(admin_auth.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to Kiddo App API",
        "docs": "/docs",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "firebase_admin_initialized": is_firebase_admin_initialized(),
    }


def create_default_data():
    """Create default data for the application."""
    from app.database import SessionLocal
    from app.models.models import GameType, Task, TaskCategory, TaskPriority, TaskStatus, TaskTemplate, User, UserRole
    from app.core.security import hash_password

    db = SessionLocal()
    try:
        # Create default users
        seed_password = "password123"
        if len(seed_password.encode("utf-8")) > 72:
            seed_password = seed_password[:72]
        default_password = hash_password(seed_password)
        parent = db.query(User).filter(User.email == "parent@kiddo.com").first()
        if not parent:
            parent = User(
                name="Parent",
                email="parent@kiddo.com",
                password_hash=default_password,
                role=UserRole.PARENT
            )
            db.add(parent)
            db.flush()

        kid = db.query(User).filter(User.email == "kid@kiddo.com").first()
        if not kid:
            kid = User(
                name="Kid",
                email="kid@kiddo.com",
                password_hash=default_password,
                role=UserRole.KID,
                parent_id=parent.id if parent else None
            )
            db.add(kid)

        # Create default categories
        categories = [
            {"name": "Disciplinary", "icon": "📋", "color_code": "#FF6B6B", "description": "Building good habits and discipline"},
            {"name": "Physical", "icon": "🏃", "color_code": "#4ECDC4", "description": "Exercise and physical activities"},
            {"name": "Spiritual", "icon": "🙏", "color_code": "#9B59B6", "description": "Spiritual growth and meditation"},
            {"name": "Educational", "icon": "📚", "color_code": "#3498DB", "description": "Learning and educational tasks"},
            {"name": "Household", "icon": "🏠", "color_code": "#F39C12", "description": "Chores and household responsibilities"},
        ]

        for cat_data in categories:
            existing = db.query(TaskCategory).filter(TaskCategory.name == cat_data["name"]).first()
            if not existing:
                category = TaskCategory(**cat_data)
                db.add(category)

        db.flush()

        # Create default task templates
        category_map = {c.name: c.id for c in db.query(TaskCategory).all()}
        templates = [
            {"title": "Clean your room", "description": "Make bed and organize toys", "category": "Household", "suggested_points": 20, "age_min": 6, "age_max": 12},
            {"title": "Read for 20 minutes", "description": "Pick any book and read", "category": "Educational", "suggested_points": 15, "age_min": 6, "age_max": 14},
            {"title": "Practice piano", "description": "Practice for 30 minutes", "category": "Educational", "suggested_points": 25, "age_min": 7, "age_max": 16},
            {"title": "Daily exercise", "description": "20 minutes of activity", "category": "Physical", "suggested_points": 15, "age_min": 6, "age_max": 14},
            {"title": "Good manners", "description": "Say please and thank you", "category": "Disciplinary", "suggested_points": 10, "age_min": 4, "age_max": 12},
            {"title": "Prayer time", "description": "5 minutes of prayer/meditation", "category": "Spiritual", "suggested_points": 10, "age_min": 6, "age_max": 14},
        ]

        for t in templates:
            exists = db.query(TaskTemplate).filter(TaskTemplate.title == t["title"]).first()
            if not exists:
                template = TaskTemplate(
                    title=t["title"],
                    description=t["description"],
                    category_id=category_map.get(t["category"]),
                    suggested_points=t["suggested_points"],
                    age_min=t["age_min"],
                    age_max=t["age_max"],
                )
                db.add(template)

        db.flush()

        # Create sample tasks for the seeded kid
        if parent and kid:
            sample_tasks = [
                {"title": "Clean your room", "description": "Make bed and organize toys", "status": TaskStatus.PENDING, "priority": TaskPriority.HIGH, "points": 20},
                {"title": "Read for 20 minutes", "description": "Pick any book and read", "status": TaskStatus.IN_PROGRESS, "priority": TaskPriority.MEDIUM, "points": 15},
                {"title": "Daily exercise", "description": "20 minutes of activity", "status": TaskStatus.AWAITING_APPROVAL, "priority": TaskPriority.MEDIUM, "points": 15},
            ]
            for st in sample_tasks:
                exists = db.query(Task).filter(
                    Task.title == st["title"],
                    Task.assigned_to == kid.id
                ).first()
                if not exists:
                    task = Task(
                        title=st["title"],
                        description=st["description"],
                        assigned_to=kid.id,
                        created_by=parent.id,
                        status=st["status"],
                        priority=st["priority"],
                        points=st["points"],
                    )
                    db.add(task)

        # Create default game types
        game_types = [
            {"name": "chess", "description": "Chess puzzles and challenges", "points_reward_base": 25, "icon": "♟️"},
            {"name": "math", "description": "Math quiz and calculations", "points_reward_base": 10, "icon": "🔢"},
            {"name": "memory", "description": "Memory matching game", "points_reward_base": 20, "icon": "🧠"},
            {"name": "words", "description": "Word games and spelling", "points_reward_base": 10, "icon": "📝"},
        ]

        for gt_data in game_types:
            existing = db.query(GameType).filter(GameType.name == gt_data["name"]).first()
            if not existing:
                game_type = GameType(**gt_data)
                db.add(game_type)

        db.commit()
    except Exception as e:
        print(f"Error creating default data: {e}")
        db.rollback()
    finally:
        db.close()


@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    initialize_firebase_admin()
    create_default_data()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
