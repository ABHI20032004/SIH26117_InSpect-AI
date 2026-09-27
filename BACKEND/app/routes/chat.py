from fastapi import (
    APIRouter,
    HTTPException,
    UploadFile,
    File,
    Form,
    Depends
)

from pydantic import BaseModel
from typing import Optional
import os
import uuid
import json
from datetime import datetime

from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Chat, ChatMessage, User
from .auth import get_current_user
from ..services.model_router import route_question


router = APIRouter(
    prefix="/api/chat",
    tags=["AI Chat"]
)


class ChatRequest(BaseModel):

    message: str

    # Optional manual override.
    # Examples:
    # "general"
    # "code"
    # "pdf"
    # "ocr"
    mode: Optional[str] = None

    # Context information
    has_pdf: bool = False
    has_image: bool = False


# =========================================================
# IMAGE UPLOAD DIRECTORY
# =========================================================

CHAT_IMAGE_DIR = "data/chat_images"

os.makedirs(
    CHAT_IMAGE_DIR,
    exist_ok=True
)


# =========================================================
# CHAT ENDPOINT
# =========================================================

@router.post("")
async def chat(

    message: str = Form(...),

    mode: Optional[str] = Form(None),

    has_pdf: bool = Form(False),

    has_image: bool = Form(False),

    pdf_id: Optional[int] = Form(None),

    chat_id: Optional[int] = Form(None),

    image: Optional[UploadFile] = File(None),

    current_user: User = Depends(get_current_user),

    db: Session = Depends(get_db)

):

    question = message.strip()

    if not question:

        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty"
        )


    # =====================================================
    # GET OR CREATE CHAT
    # =====================================================

    if chat_id is not None:

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

    else:

        # Automatically create a new chat
        # when frontend does not provide chat_id.

        title = question[:50]

        if len(question) > 50:
            title += "..."

        chat = Chat(
            user_id=current_user.id,
            title=title
        )

        db.add(chat)
        db.commit()
        db.refresh(chat)

        chat_id = chat.id


    # =====================================================
    # IMAGE PATH
    # =====================================================

    image_path = None


    try:

        # =================================================
        # SAVE IMAGE FIRST
        # =================================================

        if image is not None:

            extension = os.path.splitext(
                image.filename or ""
            )[1].lower()

            if not extension:
                extension = ".png"

            filename = (
                f"{uuid.uuid4().hex}"
                f"{extension}"
            )

            image_path = os.path.join(
                CHAT_IMAGE_DIR,
                filename
            )

            with open(
                image_path,
                "wb"
            ) as buffer:

                while True:

                    chunk = await image.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    buffer.write(chunk)

            has_image = True


        # =================================================
        # SAVE USER MESSAGE
        # =================================================

        user_message = ChatMessage(

            chat_id=chat.id,

            role="user",

            content=question,

            model=None,

            message_type="user",

            sources=None,

            image_path=image_path

        )

        db.add(user_message)

        db.commit()

        db.refresh(user_message)


        # =================================================
        # AUTOMATIC MODEL ROUTING
        # =================================================

        result = route_question(

            question,

            has_pdf=has_pdf,

            has_image=has_image,

            requested_mode=mode,

            image_path=image_path,

            pdf_id=pdf_id
        )


        # =================================================
        # GET AI RESPONSE DATA
        # =================================================

        answer = result.get(
            "answer",
            "I couldn't generate an answer."
        )

        model = result.get(
            "model",
            ""
        )

        message_type = result.get(
            "type",
            "general"
        )

        sources = result.get(
            "sources",
            []
        )


        # =================================================
        # SAVE AI MESSAGE
        # =================================================

        assistant_message = ChatMessage(

            chat_id=chat.id,

            role="assistant",

            content=answer,

            model=model,

            message_type=message_type,

            sources=json.dumps(
                sources
            ) if sources else None

        )

        db.add(assistant_message)


        # =================================================
        # UPDATE CHAT TIMESTAMP
        # =================================================

        chat.updated_at = datetime.utcnow()


        db.commit()

        db.refresh(
            assistant_message
        )


        # =================================================
        # RETURN RESPONSE TO FRONTEND
        # =================================================

        return {

            "success": True,

            "chat_id": chat.id,

            "message_id":
                assistant_message.id,

            "type":
                message_type,

            "model":
                model,

            "answer":
                answer,

            "sources":
                sources,

            "routing_reason":
                result.get(
                    "routing_reason",
                    ""
                )
        }


    except Exception as e:

        db.rollback()

        # If something fails before the chat is
        # successfully saved, remove the image.

        if image_path and os.path.exists(
            image_path
        ):

            try:

                os.remove(
                    image_path
                )

            except Exception:
                pass

        raise HTTPException(

            status_code=500,

            detail=str(e)

        )