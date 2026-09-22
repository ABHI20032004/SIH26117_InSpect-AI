from datetime import datetime
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Chat, ChatMessage, User
from .auth import get_current_user


router = APIRouter(
    prefix="/api/chats",
    tags=["Chat History"]
)


# =========================================================
# REQUEST SCHEMAS
# =========================================================

class CreateChatRequest(BaseModel):
    title: str = "New Chat"


class RenameChatRequest(BaseModel):
    title: str


# =========================================================
# CREATE CHAT
# =========================================================

@router.post("")
def create_chat(
    data: CreateChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    chat = Chat(
        user_id=current_user.id,
        title=data.title.strip() or "New Chat"
    )

    db.add(chat)
    db.commit()
    db.refresh(chat)

    return {
        "success": True,
        "chat": {
            "id": chat.id,
            "title": chat.title,
            "created_at": chat.created_at,
            "updated_at": chat.updated_at
        }
    }


# =========================================================
# GET ALL CHATS
# =========================================================

@router.get("")
def get_chats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    chats = (
        db.query(Chat)
        .filter(
            Chat.user_id == current_user.id
        )
        .order_by(
            Chat.updated_at.desc()
        )
        .all()
    )

    return {
        "success": True,
        "chats": [
            {
                "id": chat.id,
                "title": chat.title,
                "created_at": chat.created_at,
                "updated_at": chat.updated_at
            }
            for chat in chats
        ]
    }


# =========================================================
# GET ONE CHAT WITH MESSAGES
# =========================================================

@router.get("/{chat_id}")
def get_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    chat = (
        db.query(Chat)
        .filter(
            Chat.id == chat_id,
            Chat.user_id == current_user.id
        )
        .first()
    )

    if not chat:

        raise HTTPException(
            status_code=404,
            detail="Chat not found"
        )

    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.chat_id == chat.id
        )
        .order_by(
            ChatMessage.created_at.asc()
        )
        .all()
    )

    formatted_messages = []

    for message in messages:

        sources = []

        if message.sources:

            try:
                sources = json.loads(
                    message.sources
                )

            except Exception:
                sources = []

        formatted_messages.append({
    "id": message.id,
    "role": message.role,
    "content": message.content,
    "model": message.model,
    "type": message.message_type,
    "sources": sources,
    "image_path": message.image_path,
    "created_at": message.created_at
})

    return {

        "success": True,

        "chat": {

            "id": chat.id,

            "title": chat.title,

            "created_at": chat.created_at,

            "updated_at": chat.updated_at,

            "messages": formatted_messages

        }

    }


# =========================================================
# RENAME CHAT
# =========================================================

@router.patch("/{chat_id}")
def rename_chat(
    chat_id: int,
    data: RenameChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    chat = (
        db.query(Chat)
        .filter(
            Chat.id == chat_id,
            Chat.user_id == current_user.id
        )
        .first()
    )

    if not chat:

        raise HTTPException(
            status_code=404,
            detail="Chat not found"
        )

    title = data.title.strip()

    if not title:

        raise HTTPException(
            status_code=400,
            detail="Chat title cannot be empty"
        )

    chat.title = title
    chat.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(chat)

    return {

        "success": True,

        "chat": {

            "id": chat.id,

            "title": chat.title,

            "updated_at": chat.updated_at

        }

    }


# =========================================================
# DELETE CHAT
# =========================================================

@router.delete("/{chat_id}")
def delete_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    chat = (
        db.query(Chat)
        .filter(
            Chat.id == chat_id,
            Chat.user_id == current_user.id
        )
        .first()
    )

    if not chat:

        raise HTTPException(
            status_code=404,
            detail="Chat not found"
        )

    # Delete messages belonging to chat
    db.query(ChatMessage).filter(
        ChatMessage.chat_id == chat.id
    ).delete(
        synchronize_session=False
    )

    # Delete chat
    db.delete(chat)

    db.commit()

    return {

        "success": True,

        "message":
            "Chat deleted successfully"

    }