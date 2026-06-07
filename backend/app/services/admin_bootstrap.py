from sqlalchemy.orm import Session

from app.models.all_models import User
from app.services.auth_service import get_password_hash, verify_password


def ensure_super_admin(db: Session, username: str, password: str) -> None:
    """Keep the configured super-admin credentials as the source of truth."""
    admin_user = db.query(User).filter(User.username == username).first()
    if not admin_user:
        db.add(User(
            username=username,
            hashed_password=get_password_hash(password),
            role="admin",
        ))
        db.commit()
        return

    changed = False
    if admin_user.role != "admin":
        admin_user.role = "admin"
        changed = True
    if not verify_password(password, admin_user.hashed_password):
        admin_user.hashed_password = get_password_hash(password)
        changed = True
    if changed:
        db.commit()
