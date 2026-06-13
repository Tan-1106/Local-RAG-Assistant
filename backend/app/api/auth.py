import secrets
from typing                             import Optional
from sqlalchemy.orm                     import Session
from fastapi                            import HTTPException
from fastapi                            import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.security                   import OAuth2PasswordRequestForm
from app.models.all_models              import User
from app.db.session                     import get_db
from app.schemas.auth                   import UserRegister, UserResponse
from app.config                         import settings
from app.repositories.user_repository   import UserRepository
from app.services.auth_service          import (register_user, authenticate_user, create_access_token, get_current_user)
from app.services.auth_session          import AuthSessionService, get_auth_session_service
from app.services.rate_limit            import RateLimit, RateLimiter, client_ip, get_rate_limiter


router = APIRouter(prefix="/auth", tags=["Authentication"])


def set_csrf_cookie(response: Response, csrf_token: str, max_age: int) -> None:
    """Set the CSRF cookie and expose the matching token to the frontend."""
    response.set_cookie(
        key=settings.AUTH_CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=max_age,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )
    response.headers["X-CSRF-Token"] = csrf_token
    response.headers["Cache-Control"] = "no-store"


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
) -> None:
    access_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    refresh_max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=access_token,
        max_age=access_max_age,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path=settings.AUTH_COOKIE_PATH,
    )
    response.set_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/api/auth",
    )
    set_csrf_cookie(response, secrets.token_urlsafe(32), refresh_max_age)


def clear_auth_cookies(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        path=settings.AUTH_COOKIE_PATH,
        secure=settings.AUTH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
    response.delete_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        path="/api/auth",
        secure=settings.AUTH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
    response.delete_cookie(
        key=settings.AUTH_CSRF_COOKIE_NAME,
        path="/",
        secure=settings.AUTH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )


# User registration endpoint
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    request: Request,
    user_in: UserRegister,
    db: Session = Depends(get_db),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
):
    """
    Register a new user account.

    Args:
        user_in (UserRegister): The registration payload containing username and password.
        db (Session, optional): The database session dependency.

    Returns:
        UserResponse: The newly created user details.
    """
    rate_limiter.enforce(
        "register:ip",
        client_ip(request),
        RateLimit(settings.RATE_LIMIT_REGISTER_IP_PER_HOUR, 3600),
    )
    return register_user(db, user_in)


# User login endpoint to authenticate and create a cookie-backed session
@router.post("/login", response_model=UserResponse)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    auth_sessions: AuthSessionService = Depends(get_auth_session_service),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
):
    """
    Authenticate credentials and store the signed JWT in an HttpOnly cookie.

    Args:
        form_data (OAuth2PasswordRequestForm, optional): Form data containing username and password.
        db (Session, optional): The database session dependency.

    Returns:
        UserResponse: The authenticated user's profile.
    """
    rate_limiter.enforce(
        "login:ip",
        client_ip(request),
        RateLimit(settings.RATE_LIMIT_LOGIN_IP_PER_MINUTE, 60),
    )
    rate_limiter.enforce(
        "login:username",
        form_data.username.strip().lower(),
        RateLimit(settings.RATE_LIMIT_LOGIN_USERNAME_PER_15_MINUTES, 900),
    )

    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    
    auth_session = auth_sessions.create(user.username)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "sid": auth_session.session_id,
            "type": "access",
        }
    )
    set_auth_cookies(response, access_token, auth_session.refresh_token)
    return user


@router.post("/refresh", response_model=UserResponse)
def refresh(
    response: Response,
    refresh_token: Optional[str] = Cookie(
        default=None,
        alias=settings.AUTH_REFRESH_COOKIE_NAME,
    ),
    db: Session = Depends(get_db),
    auth_sessions: AuthSessionService = Depends(get_auth_session_service),
):
    """Rotate the refresh token and issue a new short-lived access token."""
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh session not found")

    auth_session = auth_sessions.rotate(refresh_token)
    if not auth_session:
        raise HTTPException(status_code=401, detail="Refresh session is invalid")

    user = UserRepository.get_by_username(db, auth_session.username)
    if not user:
        auth_sessions.revoke(session_id=auth_session.session_id)
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="User no longer exists")

    access_token = create_access_token(
        data={
            "sub": user.username,
            "sid": auth_session.session_id,
            "type": "access",
        }
    )
    set_auth_cookies(response, access_token, auth_session.refresh_token)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(
        default=None,
        alias=settings.AUTH_REFRESH_COOKIE_NAME,
    ),
    auth_sessions: AuthSessionService = Depends(get_auth_session_service),
):
    """Clear the authentication and CSRF cookies."""
    auth_sessions.revoke(refresh_token=refresh_token)
    clear_auth_cookies(response)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    response: Response,
    current_user: User = Depends(get_current_user),
    auth_sessions: AuthSessionService = Depends(get_auth_session_service),
):
    """Revoke every active session belonging to the current user."""
    auth_sessions.revoke_all(current_user.username)
    clear_auth_cookies(response)


# Endpoint to get current user details using JWT token
@router.get("/me", response_model=UserResponse)
def get_me(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user)
):
    """
    Fetch current logged-in user details.

    Args:
        current_user (User, optional): The authenticated user dependency.

    Returns:
        UserResponse: The current user's profile details.
    """
    csrf_token = request.cookies.get(settings.AUTH_CSRF_COOKIE_NAME)
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        set_csrf_cookie(
            response,
            csrf_token,
            settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )
    else:
        response.headers["X-CSRF-Token"] = csrf_token
        response.headers["Cache-Control"] = "no-store"
    return current_user
