import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Overridable so a container can put the file on a mounted volume. Without that the
# database sits on an ephemeral disk and resets on every restart.
DATABASE_PATH = os.environ.get("DATABASE_PATH", "./disputes.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Background gather tasks hold a connection across their pacing delay, so the default
# pool of 5 + 10 overflow is exhausted by a couple of dozen simultaneous runs and
# ordinary polls start failing with QueuePool timeouts. `timeout` is SQLite's own
# busy-wait for a locked file; `pool_timeout` is how long a request waits for a
# connection before giving up.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 15},
    pool_size=20,
    max_overflow=40,
    pool_timeout=30,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
