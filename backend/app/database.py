from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./disputes.db"

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
