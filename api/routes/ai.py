from fastapi import APIRouter, Depends, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from db.connection import get_db_dependency
from db.models import Batch, Subject, Lecture, App, Student
from api.auth import optional_student_auth

router = APIRouter(prefix="/ai", tags=["AI Assistant"])

@router.post("/query")
@router.post("/ask")
async def query_ai_assistant(
    payload: dict = Body(...),
    student: Student = Depends(optional_student_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    Course Wallah Student AI Assistant.
    Provides intelligent guidance, curriculum lookup, and navigation assistance
    strictly within public or student-authorized course bounds.
    """
    message = payload.get("message") or payload.get("query") or ""
    message = message.strip()
    if not message:
        msg = "Hello! I am your Course Wallah Learning Assistant. You can ask me about available courses, find specific subjects or lectures, or get help navigating your curriculum."
        return {
            "reply": msg,
            "answer": msg,
            "actions": []
        }

    q_lower = message.lower()
    actions = []

    # 1. Check if asking about personal batches / continue learning
    if any(k in q_lower for k in ["my batch", "my course", "enrolled", "my lectures", "continue learning"]):
        if student:
            # Query student enrolled batches
            from db.models import StudentBatchAccess
            stmt = (
                select(Batch)
                .join(StudentBatchAccess, StudentBatchAccess.batch_id == Batch.id)
                .where(
                    and_(
                        StudentBatchAccess.student_id == student.id,
                        StudentBatchAccess.status == "ACTIVE",
                        Batch.status == "ACTIVE"
                    )
                )
            )
            res = await db.execute(stmt)
            enrolled = res.scalars().all()
            if enrolled:
                batch_names = ", ".join([b.name for b in enrolled])
                reply = f"Welcome back, {student.name}! You are currently enrolled in: **{batch_names}**. You can continue watching lectures anytime."
                for b in enrolled:
                    actions.append({
                        "label": f"Open {b.name}",
                        "href": f"/batches/{b.slug}"
                    })
                return {"reply": reply, "answer": reply, "actions": actions}
            else:
                reply = f"Hi {student.name}, you are not enrolled in any batches yet. You can browse the Course Catalog to start learning!"
                return {
                    "reply": reply,
                    "answer": reply,
                    "actions": [{"label": "Explore Courses", "href": "/#courses"}]
                }
        else:
            reply = "Please log in to view your enrolled batches and personal learning history."
            return {
                "reply": reply,
                "answer": reply,
                "actions": [
                    {"label": "Log In", "href": "/login"},
                    {"label": "Register", "href": "/register"}
                ]
            }

    # 2. Check if asking about notes / PDF access
    if any(k in q_lower for k in ["notes", "pdf", "handwritten", "materials"]):
        reply = "All Course Wallah lectures feature high-fidelity study notes. When you open any lecture with notes available, simply click **'Open Notes'** to read directly in our full-screen reader."
        return {
            "reply": reply,
            "answer": reply,
            "actions": [{"label": "Explore Courses", "href": "/#courses"}]
        }

    # 3. Check if asking about support / contact
    if any(k in q_lower for k in ["contact", "support", "help", "email", "issue", "problem"]):
        reply = "Our student support team is ready to help! You can send us a message directly via our Contact page."
        return {
            "reply": reply,
            "answer": reply,
            "actions": [{"label": "Contact Support", "href": "/contact"}]
        }

    # 4. Search relevant batches or subjects matching keywords
    batch_stmt = select(Batch).where(and_(Batch.status == "ACTIVE", Batch.name.ilike(f"%{q_lower}%"))).limit(3)
    batch_res = await db.execute(batch_stmt)
    matching_batches = batch_res.scalars().all()

    if matching_batches:
        names = ", ".join([b.name for b in matching_batches])
        reply = f"I found the following batches matching your search: **{names}**."
        for b in matching_batches:
            actions.append({"label": f"Open {b.name}", "href": f"/batches/{b.slug}"})
        return {"reply": reply, "answer": reply, "actions": actions}

    # 5. Search relevant lectures
    lec_stmt = select(Lecture).where(Lecture.title.ilike(f"%{q_lower}%")).limit(3)
    lec_res = await db.execute(lec_stmt)
    matching_lectures = lec_res.scalars().all()

    if matching_lectures:
        reply = "Here are the lectures related to your topic:"
        for l in matching_lectures:
            actions.append({"label": f"#{l.lecture_index} - {l.title}", "href": f"/lectures/{l.id}"})
        return {"reply": reply, "answer": reply, "actions": actions}

    # 6. General intelligent learning assistant fallback
    reply = f"I understand you are asking about: '{message}'. You can explore our structured curriculum, search for specific lectures, or check your profile."
    return {
        "reply": reply,
        "answer": reply,
        "actions": [
            {"label": "Explore Courses", "href": "/#courses"},
            {"label": "Search Catalog", "href": "/search"}
        ]
    }
