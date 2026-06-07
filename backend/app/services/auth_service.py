import jwt
import bcrypt
from typing                             import Optional
from datetime                           import datetime, timedelta
from sqlalchemy.orm                     import Session
from fastapi                            import Depends, HTTPException, status
from fastapi.security                   import OAuth2PasswordBearer
from app.config                         import settings
from app.db.session                     import get_db
from app.models.all_models              import User
from app.schemas.auth                   import UserRegister
from app.repositories.user_repository   import UserRepository


# JWT authentication configuration
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify standard text password against stored hash using bcrypt directly.

    Args:
        plain_password (str): The raw text password.
        hashed_password (str): The stored hashed password.

    Returns:
        bool: True if passwords match, False otherwise.
    """
    try:
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """
    Generate bcrypt password hash from raw string using bcrypt directly.

    Args:
        password (str): The raw text password to hash.

    Returns:
        str: The bcrypt hash string.
    """
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Generate signed JWT token containing custom claims (username).

    Args:
        data (dict): Data payload to embed in the token (e.g., {"sub": "username"}).
        expires_delta (Optional[timedelta]): Custom expiration time. Defaults to ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        str: The signed JWT access token.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """
    Authenticate a user by checking their username and password.

    Args:
        db (Session): The database session.
        username (str): The username provided.
        password (str): The password provided.

    Returns:
        Optional[User]: The authenticated User object if credentials are valid, otherwise None.
    """
    user = UserRepository.get_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def register_user(db: Session, user_in: UserRegister) -> User:
    """
    Registers a new user after verifying the username is unique.

    Args:
        db (Session): The database session.
        user_in (UserRegister): Registration data (username and password).

    Returns:
        User: The newly created User object.
        
    Raises:
        HTTPException: If the username is already registered.
    """
    existing_user = UserRepository.get_by_username(db, user_in.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    hashed_password = get_password_hash(user_in.password)
    return UserRepository.create(db, username=user_in.username, hashed_password=hashed_password)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """
    FastAPI dependency to extract JWT from request header, validate claims,
    and fetch the authenticated User object from the database.

    Args:
        token (str): The extracted JWT from the Authorization header.
        db (Session): The database session.

    Returns:
        User: The currently authenticated User object.
        
    Raises:
        HTTPException: If the token is invalid, expired, or the user does not exist.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    user = UserRepository.get_by_username(db, username)
    if user is None:
        raise credentials_exception
    return user


def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    FastAPI dependency to verify that the current user has the 'admin' role.

    Args:
        current_user (User): The authenticated user.

    Returns:
        User: The authenticated admin User object.

    Raises:
        HTTPException: If the user role is not 'admin'.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user
