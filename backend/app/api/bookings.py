"""The user's bookings, for the bookings page. Booking itself happens only through the chat."""

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.db.models import Booking
from app.itineraries.views import itinerary_summary
from app.schemas.itinerary import BookingOut

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


@router.get("")
def list_bookings(user: CurrentUser, db: DbSession) -> list[BookingOut]:
    bookings = db.scalars(select(Booking).where(Booking.user_id == user.id)
                          .order_by(Booking.booked_at.desc(), Booking.id.desc()))
    return [BookingOut(booking_id=b.id, status=b.status, booked_at=b.booked_at, total=b.total_cost,
                       itinerary=itinerary_summary(db, b.itinerary)) for b in bookings]
