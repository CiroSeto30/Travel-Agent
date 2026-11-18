"""An itinerary in detail, and the activity choice of the details panel."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.db.models import Itinerary
from app.itineraries.selection import SelectionError, update_activities
from app.itineraries.views import itinerary_details
from app.schemas.itinerary import ActivityChoice, ItineraryDetails

router = APIRouter(prefix="/api/itineraries", tags=["itineraries"])


@router.get("/{itinerary_id}")
def get_itinerary(itinerary_id: int, user: CurrentUser, db: DbSession) -> ItineraryDetails:
    itinerary = db.scalar(select(Itinerary).where(Itinerary.id == itinerary_id, Itinerary.user_id == user.id))
    if itinerary is None:  # someone else's itinerary is, for this user, one that does not exist
        raise HTTPException(status.HTTP_404_NOT_FOUND, {"code": "not_found", "message": "Itinerary not found"})
    return itinerary_details(db, itinerary)


@router.put("/{itinerary_id}/activities")
def put_activities(itinerary_id: int, selection: list[ActivityChoice], user: CurrentUser,
                   db: DbSession) -> ItineraryDetails:
    try:
        itinerary = update_activities(db, user_id=user.id, itinerary_id=itinerary_id,
                                      selection=[(c.day, c.activity_id) for c in selection])
    except SelectionError as e:  # every check runs before any change: nothing to undo
        raise HTTPException(e.status, {"code": e.code, "message": str(e)}) from None
    db.commit()
    return itinerary_details(db, itinerary)
