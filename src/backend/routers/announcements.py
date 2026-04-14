"""
Announcement endpoints for the High School Management System API
"""

from datetime import date
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementUpsert(BaseModel):
    message: str = Field(min_length=1, max_length=280)
    expires_at: str
    starts_at: Optional[str] = None
    teacher_username: str


def _validate_teacher(teacher_username: str) -> None:
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Authentication required for this action")


def _parse_iso_date(value: Optional[str], field_name: str) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must use YYYY-MM-DD format (received: {value})"
        ) from exc


def _format_announcement(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": doc["_id"],
        "message": doc["message"],
        "starts_at": doc.get("starts_at"),
        "expires_at": doc["expires_at"],
        "created_at": doc.get("created_at")
    }


@router.get("/active", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Return only announcements active for the current date."""
    today = date.today().isoformat()

    query = {
        "$and": [
            {"expires_at": {"$gte": today}},
            {
                "$or": [
                    {"starts_at": None},
                    {"starts_at": {"$exists": False}},
                    {"starts_at": {"$lte": today}}
                ]
            }
        ]
    }

    docs = announcements_collection.find(query).sort("expires_at", 1)
    return [_format_announcement(doc) for doc in docs]


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def list_announcements(teacher_username: str) -> List[Dict[str, Any]]:
    """List all announcements for management UI (authentication required)."""
    _validate_teacher(teacher_username)
    docs = announcements_collection.find({}).sort("created_at", -1)
    return [_format_announcement(doc) for doc in docs]


@router.post("", response_model=Dict[str, Any])
@router.post("/", response_model=Dict[str, Any])
def create_announcement(payload: AnnouncementUpsert) -> Dict[str, Any]:
    """Create a new announcement (authentication required)."""
    _validate_teacher(payload.teacher_username)

    starts_at = _parse_iso_date(payload.starts_at, "starts_at")
    expires_at = _parse_iso_date(payload.expires_at, "expires_at")

    if not expires_at:
        raise HTTPException(status_code=400, detail="expires_at is required")

    if starts_at and starts_at > expires_at:
        raise HTTPException(status_code=400, detail="starts_at cannot be after expires_at")

    doc = {
        "_id": str(uuid4()),
        "message": payload.message.strip(),
        "starts_at": starts_at.isoformat() if starts_at else None,
        "expires_at": expires_at.isoformat(),
        "created_at": date.today().isoformat()
    }

    announcements_collection.insert_one(doc)
    return _format_announcement(doc)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(announcement_id: str, payload: AnnouncementUpsert) -> Dict[str, Any]:
    """Update an existing announcement (authentication required)."""
    _validate_teacher(payload.teacher_username)

    starts_at = _parse_iso_date(payload.starts_at, "starts_at")
    expires_at = _parse_iso_date(payload.expires_at, "expires_at")

    if not expires_at:
        raise HTTPException(status_code=400, detail="expires_at is required")

    if starts_at and starts_at > expires_at:
        raise HTTPException(status_code=400, detail="starts_at cannot be after expires_at")

    update_doc = {
        "message": payload.message.strip(),
        "starts_at": starts_at.isoformat() if starts_at else None,
        "expires_at": expires_at.isoformat()
    }

    result = announcements_collection.update_one(
        {"_id": announcement_id},
        {"$set": update_doc}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": announcement_id})
    if updated is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return _format_announcement(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(announcement_id: str, teacher_username: str) -> Dict[str, str]:
    """Delete announcement (authentication required)."""
    _validate_teacher(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}