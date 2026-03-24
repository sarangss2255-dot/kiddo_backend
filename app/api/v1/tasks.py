"""Task endpoints."""
import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import User, Task, TaskCategory, TaskTemplate, TaskStatus, UserRole
from app.schemas import (
    TaskCreate, TaskUpdate, TaskResponse, TaskApprovalRequest,
    TaskStatusUpdate, TaskCategoryResponse, TaskTemplateResponse,
    TaskTemplateCreate, TaskTemplateUpdate
)
from app.api.deps import get_current_user, get_current_parent, get_current_kid_or_parent

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ============= Task Categories =============
@router.get("/categories", response_model=List[TaskCategoryResponse])
async def list_categories(
    db: Session = Depends(get_db)
):
    """List all task categories."""
    categories = db.query(TaskCategory).all()
    return [TaskCategoryResponse.model_validate(cat) for cat in categories]


# ============= Task Templates =============
@router.get("/templates", response_model=List[TaskTemplateResponse])
async def list_templates(
    category_id: Optional[str] = None,
    age: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List task templates, optionally filtered by category and age."""
    query = db.query(TaskTemplate).filter(TaskTemplate.is_active == True)

    if category_id:
        query = query.filter(TaskTemplate.category_id == category_id)

    if age:
        query = query.filter(
            TaskTemplate.age_min <= age,
            TaskTemplate.age_max >= age
        )

    templates = query.all()
    return [TaskTemplateResponse.model_validate(t) for t in templates]


@router.post("/templates", response_model=TaskTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    template_data: TaskTemplateCreate,
    current_user: User = Depends(get_current_parent),
    db: Session = Depends(get_db)
):
    """Create a new task template (parent only)."""
    template = TaskTemplate(**template_data.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return TaskTemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=TaskTemplateResponse)
async def update_template(
    template_id: str,
    template_data: TaskTemplateUpdate,
    current_user: User = Depends(get_current_parent),
    db: Session = Depends(get_db)
):
    """Update a task template (parent only)."""
    template = db.query(TaskTemplate).filter(TaskTemplate.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    update_data = template_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)

    db.commit()
    db.refresh(template)
    return TaskTemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_parent),
    db: Session = Depends(get_db)
):
    """Deactivate a task template (parent only)."""
    template = db.query(TaskTemplate).filter(TaskTemplate.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    template.is_active = False
    db.commit()
    return {"message": "Template deactivated successfully"}


# ============= Tasks =============
@router.get("/", response_model=List[TaskResponse])
async def list_tasks(
    status: Optional[TaskStatus] = None,
    category_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List tasks. Parents see their children's tasks, kids see their own."""
    query = db.query(Task)

    if current_user.role == UserRole.KID:
        query = query.filter(Task.assigned_to == current_user.id)
    elif current_user.role == UserRole.PARENT:
        # Get children IDs
        children_ids = [child.id for child in current_user.children]
        children_ids.append(current_user.id)  # Include parent's own tasks
        query = query.filter(Task.assigned_to.in_(children_ids) | Task.created_by == current_user.id)
    # Admins see all tasks

    if status:
        query = query.filter(Task.status == status)
    if category_id:
        query = query.filter(Task.category_id == category_id)
    if assigned_to:
        query = query.filter(Task.assigned_to == assigned_to)

    tasks = query.order_by(Task.created_at.desc()).all()
    return [TaskResponse.model_validate(task) for task in tasks]


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_parent),
    db: Session = Depends(get_db)
):
    """Create a new task (parent only)."""
    # Verify assigned user is a child of the parent
    assigned_user = db.query(User).filter(User.id == task_data.assigned_to).first()
    if not assigned_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assigned user not found"
        )

    if current_user.role == UserRole.PARENT:
        if assigned_user.parent_id != current_user.id and assigned_user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only assign tasks to your children"
            )

    task = Task(
        **task_data.model_dump(),
        created_by=current_user.id
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return TaskResponse.model_validate(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    # Check access
    if current_user.role == UserRole.KID and task.assigned_to != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return TaskResponse.model_validate(task)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    task_data: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    # Check access
    if current_user.role == UserRole.KID:
        if task.assigned_to != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        # Kids can only update status
        if task_data.status:
            # Validate status transitions
            if task.status == TaskStatus.PENDING and task_data.status == TaskStatus.IN_PROGRESS:
                task.status = TaskStatus.IN_PROGRESS
            elif task.status == TaskStatus.IN_PROGRESS and task_data.status == TaskStatus.AWAITING_APPROVAL:
                task.status = TaskStatus.AWAITING_APPROVAL
                task.completed_at = datetime.utcnow()
            elif task.status == TaskStatus.REJECTED and task_data.status == TaskStatus.IN_PROGRESS:
                task.status = TaskStatus.IN_PROGRESS
                task.rejection_reason = None
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid status transition"
                )
    else:
        # Parents can update all fields
        update_data = task_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(task, key, value)

    db.commit()
    db.refresh(task)
    return TaskResponse.model_validate(task)


@router.post("/{task_id}/approve", response_model=TaskResponse)
async def approve_task(
    task_id: str,
    approval_data: TaskApprovalRequest,
    current_user: User = Depends(get_current_parent),
    db: Session = Depends(get_db)
):
    """Approve or reject a completed task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    if task.status != TaskStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task is not awaiting approval"
        )

    # Verify this parent has access to approve
    assigned_user = db.query(User).filter(User.id == task.assigned_to).first()
    if assigned_user.parent_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only approve tasks for your children"
        )

    if approval_data.approved:
        task.status = TaskStatus.APPROVED
        task.approved_by = current_user.id
        task.approved_at = datetime.utcnow()

        # Award points
        assigned_user.points_balance += task.points
    else:
        task.status = TaskStatus.REJECTED
        task.rejection_reason = approval_data.rejection_reason

    db.commit()
    db.refresh(task)
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_parent),
    db: Session = Depends(get_db)
):
    """Delete a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    if task.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete tasks you created"
        )

    db.delete(task)
    db.commit()
    return {"message": "Task deleted successfully"}
