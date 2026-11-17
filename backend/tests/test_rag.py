from decimal import Decimal

import pytest
from qdrant_client import QdrantClient
from sqlalchemy import func, select

from app.db.models import Activity
from app.planner.planner import TripRequest, plan, rank_by_category
from app.rag.embeddings import FastEmbedder
from app.rag.index import COLLECTION, activity_text, index_activities
from app.rag.ranker import semantic_ranker
from app.rag.retriever import relevant_activities
from seed.index_activities import index_catalog
from tests.conftest import TODAY
from tests.test_planner import check_against_catalog
from tests.word_embedder import WordEmbedder

# local mode ignores payload indexes and says so; the server uses them
pytestmark = pytest.mark.filterwarnings("ignore:Payload indexes have no effect")


@pytest.fixture
def qdrant():
    client = QdrantClient(":memory:")  # Qdrant's local mode: same API, no server
    yield client
    client.close()


@pytest.fixture
def indexed(japan, qdrant):
    index_activities(qdrant, WordEmbedder(), list(japan.scalars(select(Activity))))
    return qdrant


def tokyo(s):
    return list(s.scalars(select(Activity).where(Activity.city == "Tokyo").order_by(Activity.id)))


def request(**changes):
    values = dict(country="Giappone", month=4, nights=5, travelers=2, budget=Decimal("8000"), origin="NAP")
    return TripRequest(**{**values, **changes})


def test_one_point_per_activity_with_its_payload(japan, qdrant):
    activities = list(japan.scalars(select(Activity)))
    assert index_activities(qdrant, WordEmbedder(), activities) == len(activities)
    assert index_activities(qdrant, WordEmbedder(), activities) == len(activities)  # indexing again replaces
    assert qdrant.count(COLLECTION).count == len(activities)

    a = activities[0]
    [point] = qdrant.retrieve(COLLECTION, [a.id])
    assert point.payload == {"activity_id": a.id, "name": a.name, "description": a.description,
        "country": a.country, "city": a.city, "category": a.category,
        "target": a.target, "price": float(a.price)}

def test_the_indexed_text_says_who_the_activity_is_for(japan):
    a = japan.scalars(select(Activity).where(Activity.target == "families")).first()
    text = activity_text(a)
    assert a.name in text and a.description in text and "famiglie" in text


def test_results_stay_in_the_city_and_follow_the_text(japan, indexed):
    results = relevant_activities(indexed, WordEmbedder(), "mercato del pesce e sushi all'alba", city="Tokyo", limit=5)
    assert len(results) == 5
    assert all(japan.get(Activity, i).city == "Tokyo" for i, _ in results)
    assert japan.get(Activity, results[0][0]).name == "Mercato del pesce di Toyosu all'alba"
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)


def test_ranker_puts_what_the_user_asked_for_first(japan, indexed):
    rank = semantic_ranker(indexed, WordEmbedder())
    order = rank(tokyo(japan), request(preferences="assistere all'asta del tonno al mercato del pesce"))
    assert japan.get(Activity, order[0]).name == "Mercato del pesce di Toyosu all'alba"
    assert sorted(order) == [a.id for a in tokyo(japan)]  # every activity, once


def test_chosen_categories_move_their_activities_up(japan, indexed):
    rank = semantic_ranker(indexed, WordEmbedder())
    activities = tokyo(japan)
    relax = {a.id for a in activities if a.category == "relax"}
    text = "una giornata tranquilla in città"
    before = rank(activities, request(preferences=text))
    after = rank(activities, request(preferences=text, categories=("relax",)))
    assert sum(after.index(i) for i in relax) < sum(before.index(i) for i in relax)


def test_without_preferences_the_ranker_uses_the_categories(japan, indexed):
    rank = semantic_ranker(indexed, WordEmbedder())
    req = request(categories=("food",))
    assert rank(tokyo(japan), req) == rank_by_category(tokyo(japan), req)


def test_ranker_falls_back_when_qdrant_is_unavailable(japan, qdrant):
    rank = semantic_ranker(qdrant, WordEmbedder())  # nothing indexed: the collection does not exist
    req = request(preferences="buon cibo", categories=("food",))
    assert rank(tokyo(japan), req) == rank_by_category(tokyo(japan), req)


def test_planner_with_the_semantic_ranker_keeps_every_constraint(japan, indexed):
    req = request(preferences="cerimonia del tè, templi e giardini tradizionali")
    proposals = plan(japan, req, today=TODAY, rank=semantic_ranker(indexed, WordEmbedder()))
    assert proposals
    for p in proposals:
        check_against_catalog(japan, p, req)


def test_seed_indexes_once_and_then_skips(japan, qdrant):
    embedder = WordEmbedder()
    count = japan.scalar(select(func.count()).select_from(Activity))
    assert index_catalog(japan, qdrant, embedder) == count
    assert index_catalog(japan, qdrant, embedder) is None  # already up to date


def test_the_real_model_understands_italian_preferences(japan, qdrant):
    embedder = FastEmbedder()
    try:
        embedder.embed(["prova"])
    except Exception as e:  # first run needs to download the model (about 220 MB)
        pytest.skip(f"embedding model not available: {e}")
    index_activities(qdrant, embedder, tokyo(japan))
    top = [japan.get(Activity, i).name for i, _ in
           relevant_activities(qdrant, embedder, "rilassarsi nelle acque termali", city="Tokyo", limit=3)]
    assert "Onsen urbano di Odaiba" in top
