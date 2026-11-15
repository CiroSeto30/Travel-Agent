"""Every model, imported here so that Base.metadata knows all the tables."""

from app.db.models.catalog import Activity, ActivitySlot, Airport, Flight, Hotel, RoomAvailability, RoomType

__all__ = ["Activity", "ActivitySlot", "Airport", "Flight", "Hotel", "RoomAvailability", "RoomType"]