from sqlalchemy.orm             import Session
from fastapi                    import HTTPException
from fastapi                    import APIRouter, Depends, status
from fastapi.security           import OAuth2PasswordRequestForm
from app.models.all_models      import User
from app.db.session             import get_db
from app.schemas.auth           import UserRegister, Token, UserResponse
from app.services.auth_service  import (register_user, authenticate_user, create_access_token, get_current_user)


router = APIRouter(prefix="/auth", tags=["Authentication"])

# User registration endpoint
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user account.

    Args:
        user_in (UserRegister): The registration payload containing username and password.
        db (Session, optional): The database session dependency.

    Returns:
        UserResponse: The newly created user details.
    """
    return register_user(db, user_in)


# User login endpoint to authenticate and return JWT token
@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Authenticate credentials and return a signed JWT token.

    Args:
        form_data (OAuth2PasswordRequestForm, optional): Form data containing username and password.
        db (Session, optional): The database session dependency.

    Returns:
        Token: A dictionary containing the access_token and token_type.
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generate token
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


# Endpoint to get current user details using JWT token
@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Fetch current logged-in user details.

    Args:
        current_user (User, optional): The authenticated user dependency.

    Returns:
        UserResponse: The current user's profile details.
    """
    return current_user
