"""Every model, imported here so that Base.metadata knows all the tables."""

from app.db.models.catalog import Activity, ActivitySlot, Airport, Flight, Hotel, RoomAvailability, RoomType
from app.db.models.conversation import Conversation, Message
from app.db.models.itinerary import Booking, Itinerary, ItineraryItem
from app.db.models.user import User

__all__ = [
    "Activity", "ActivitySlot", "Airport", "Booking", "Conversation", "Flight", "Hotel",
    "Itinerary", "ItineraryItem", "Message", "RoomAvailability", "RoomType", "User",
]