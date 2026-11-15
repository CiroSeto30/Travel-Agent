"""Create the tables and load the synthetic catalog into PostgreSQL.

Run from the backend/ folder:  python -m seed.load_db
Running it again does nothing: the catalog is loaded only into an empty database.
"""

from datetime import date
from pathlib import Path

from sqlalchemy import insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401  (registers every model on Base.metadata)
from app.db.base import Base
from app.db.models import Activity, ActivitySlot, Airport, Flight, Hotel, RoomAvailability, RoomType
from seed.build_catalog import Catalog, build_catalog
from seed.schema import BaseData, load_base_data

DATA_DIR = Path(__file__).resolve().parent / "data"


def init_db(engine: Engine) -> None:
    """Create every table that does not exist yet."""
    Base.metadata.create_all(engine)


def _insert_returning_ids(session: Session, model, rows: list[dict]) -> list[int]:
    stmt = insert(model).returning(model.id, sort_by_parameter_order=True)
    return list(session.scalars(stmt, rows))


def load_catalog(session: Session, catalog: Catalog, base: BaseData) -> bool:
    """Insert the whole catalog. Returns False, without touching anything, if it is already there."""
    if session.scalar(select(Airport.iata).limit(1)) is not None:
        return False

    session.execute(insert(Airport), [
        {"iata": a.iata, "city": a.city, "country": a.country} for a in base.airports
    ])
    hotel_ids = _insert_returning_ids(session, Hotel, [
        {"name": h.name, "city": h.city, "country": base.country_of(h.city), "stars": h.stars,
         "description": h.description}
        for h in base.hotels
    ])
    activity_ids = _insert_returning_ids(session, Activity, [
        {"name": a.name, "city": a.city, "country": base.country_of(a.city), "category": a.category,
         "target": a.target, "price": a.price, "duration_hours": a.duration_hours,
         "description": a.description}
        for a in base.activities
    ])

    session.execute(insert(Flight), catalog.flights)
    room_type_ids = _insert_returning_ids(session, RoomType, [
        {"hotel_id": hotel_ids[rt["hotel_index"]], "name": rt["name"], "beds": rt["beds"]}
        for rt in catalog.room_types
    ])
    session.execute(insert(RoomAvailability), [
        {"room_type_id": room_type_ids[r["room_type_index"]], "night": r["night"], "price": r["price"],
         "rooms_left": r["rooms_left"]}
        for r in catalog.room_availability
    ])
    session.execute(insert(ActivitySlot), [
        {"activity_id": activity_ids[r["activity_index"]], "day": r["day"], "spots_left": r["spots_left"]}
        for r in catalog.activity_slots
    ])
    session.flush()
    return True


def main() -> None:
    from app.db.session import SessionLocal, engine

    init_db(engine)
    base = load_base_data(DATA_DIR)
    catalog = build_catalog(base, start=date.today())
    with SessionLocal() as session:
        if not load_catalog(session, catalog, base):
            print("Catalog already loaded, nothing to do")
            return
        session.commit()
    destinations = sum(1 for a in base.airports if a.role == "destination")
    print(
        f"Loaded {destinations} destinations, {len(base.hotels)} hotels, {len(base.activities)} activities, "
        f"{len(catalog.room_types)} room types, {len(catalog.flights)} flights, "
        f"{len(catalog.room_availability)} room nights, "
        f"{len(catalog.activity_slots)} activity slots"
    )


if __name__ == "__main__":
    main()