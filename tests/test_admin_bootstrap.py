import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.db.session import Base
from app.models.all_models import User
from app.services.admin_bootstrap import ensure_super_admin
from app.services.auth_service import get_password_hash, verify_password


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_super_admin_password_tracks_configuration():
    db = make_session()
    db.add(User(
        username="admin",
        hashed_password=get_password_hash("old-password"),
        role="user",
    ))
    db.commit()

    ensure_super_admin(db, "admin", "new-password")

    admin = db.query(User).filter(User.username == "admin").one()
    assert admin.role == "admin"
    assert verify_password("new-password", admin.hashed_password)
    assert not verify_password("old-password", admin.hashed_password)
    db.close()


def test_super_admin_is_created_when_missing():
    db = make_session()

    ensure_super_admin(db, "admin", "configured-password")

    admin = db.query(User).filter(User.username == "admin").one()
    assert admin.role == "admin"
    assert verify_password("configured-password", admin.hashed_password)
    db.close()
