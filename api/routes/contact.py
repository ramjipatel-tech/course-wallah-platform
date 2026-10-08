import re
from fastapi import APIRouter, HTTPException, Body
from datetime import datetime

router = APIRouter(prefix="/contact", tags=["Contact"])

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")

@router.post("")
@router.post("/submit")
async def submit_contact_message(payload: dict = Body(...)):
    """Receives and validates student contact / inquiry submissions."""
    name = payload.get("name", "").strip()
    email = payload.get("email", "").strip()
    subject = payload.get("subject", "").strip()
    message = payload.get("message", "").strip()

    if not name or len(name) < 2:
        raise HTTPException(status_code=422, detail="Please enter your name.")

    if not email or not EMAIL_REGEX.match(email):
        raise HTTPException(status_code=422, detail="Please enter a valid email address.")

    if not message or len(message) < 5:
        raise HTTPException(status_code=422, detail="Please provide a message with at least 5 characters.")

    return {
        "ok": True,
        "status": "success",
        "message": "Thank you for reaching out! Your message has been received by our support team.",
        "timestamp": datetime.utcnow().isoformat()
    }
