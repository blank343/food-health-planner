"""Zielprofile: versioniert, nur anlegen und lesen (die Historie bleibt erhalten)."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentPerson, Db, today_local
from app.api.schemas import GoalIn, GoalOut
from app.models import GoalProfile

router = APIRouter(prefix="/me/goals", tags=["Ziele"])


@router.get("", response_model=list[GoalOut], summary="Alle Zielversionen, neueste zuerst")
def list_goals(person: CurrentPerson, db: Db):
    stmt = (
        select(GoalProfile)
        .where(GoalProfile.person_id == person.id)
        .order_by(GoalProfile.valid_from.desc(), GoalProfile.id.desc())
    )
    return list(db.scalars(stmt))


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED, summary="Neue Zielversion")
def create_goal(body: GoalIn, person: CurrentPerson, db: Db):
    data = body.model_dump()
    data["valid_from"] = data["valid_from"] or today_local()
    goal = GoalProfile(person_id=person.id, **data)
    db.add(goal)
    db.commit()
    return goal


@router.get("/active", response_model=GoalOut, summary="Zielversion, die an einem Tag gilt")
def active_goal(person: CurrentPerson, db: Db, on: date | None = None):
    day = on or today_local()
    stmt = (
        select(GoalProfile)
        .where(GoalProfile.person_id == person.id, GoalProfile.valid_from <= day)
        .order_by(GoalProfile.valid_from.desc(), GoalProfile.id.desc())
        .limit(1)
    )
    goal = db.scalar(stmt)
    if goal is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Für den {day.isoformat()} ist kein Ziel hinterlegt."
        )
    return goal
