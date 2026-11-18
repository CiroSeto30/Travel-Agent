"""The agent used by the API: created on the first chat message, with its state saved in PostgreSQL.

LangGraph's tables are created by the seed (python -m seed.load_db), with the rest of the schema.
"""

from functools import lru_cache

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy.engine import make_url

from app.agent.graph import build_graph
from app.agent.llm import LLMBrain
from app.config import get_settings


def checkpoint_conninfo(database_url: str) -> str:
    """psycopg wants a plain postgresql:// URL, without SQLAlchemy's "+psycopg" driver name."""
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


def setup_checkpointer(database_url: str) -> None:
    """Create LangGraph's own tables. Run by the seed, never during a request: the setup creates indexes
    CONCURRENTLY, which waits for every open transaction, the request's own included."""
    with PostgresSaver.from_conn_string(checkpoint_conninfo(database_url)) as saver:
        saver.setup()


@lru_cache
def get_agent():
    settings = get_settings()
    brain = LLMBrain.from_settings(settings)  # first: a missing key fails before any connection is opened
    pool = ConnectionPool(checkpoint_conninfo(settings.database_url), max_size=5, open=True,
                          kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
    return build_graph(brain, checkpointer=PostgresSaver(pool))
