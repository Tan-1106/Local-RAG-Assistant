from app.config         import settings
from sqlalchemy         import create_engine
from sqlalchemy.orm     import declarative_base, sessionmaker

# connect_args={"check_same_thread": False} is required only for SQLite
connect_args = (
    { "check_same_thread": False }
    if settings.DATABASE_URL.startswith("sqlite")
    else { }
)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """
    FastAPI dependency that provides a database session.
    Yields the session and ensures it is closed after the request completes.

    Yields:
        Session: The SQLAlchemy database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
