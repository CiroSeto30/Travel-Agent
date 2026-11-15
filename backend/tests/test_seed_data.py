import json
import shutil
from pathlib import Path

import pytest

from seed.schema import load_base_data

DATA = Path(__file__).resolve().parents[1] / "seed" / "data"


def test_base_data_is_complete():
    d = load_base_data(DATA)
    dest = [a for a in d.airports if a.role == "destination"]
    assert {a.iata for a in d.airports if a.role == "departure"} == {"NAP", "FCO", "MXP"}
    assert len({a.country for a in dest}) == 11 and len(dest) == 33
    assert "Italia" in {a.country for a in dest}
    assert not {a.city for a in dest} & {a.city for a in d.airports if a.role == "departure"}
    assert len(d.hotels) == 200 and len(d.activities) == 500
    for city in {a.city for a in dest}:
        hotels = [h for h in d.hotels if h.city == city]
        assert len(hotels) in (6, 7)
        assert any(h.stars <= 3 for h in hotels) and any(h.stars >= 4 for h in hotels)
        acts = [a for a in d.activities if a.city == city]
        assert len(acts) in (15, 16) and len({a.category for a in acts}) >= 4


def test_descriptions_are_unique():
    d = load_base_data(DATA)
    descriptions = [a.description for a in d.activities]
    assert len(set(descriptions)) == len(descriptions)


def test_hotel_in_unknown_city_is_rejected(tmp_path):
    shutil.copytree(DATA, tmp_path, dirs_exist_ok=True)
    hotels = json.loads((tmp_path / "hotels.json").read_text(encoding="utf-8"))
    hotels[0]["city"] = "Atlantide"
    (tmp_path / "hotels.json").write_text(json.dumps(hotels), encoding="utf-8")
    with pytest.raises(ValueError, match="Atlantide"):
        load_base_data(tmp_path)


def test_unknown_category_is_rejected(tmp_path):
    shutil.copytree(DATA, tmp_path, dirs_exist_ok=True)
    acts = json.loads((tmp_path / "activities.json").read_text(encoding="utf-8"))
    acts[0]["category"] = "shopping"
    (tmp_path / "activities.json").write_text(json.dumps(acts), encoding="utf-8")
    with pytest.raises(ValueError):
        load_base_data(tmp_path)