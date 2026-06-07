from pydantic import BaseModel, Field

class UserRegister(BaseModel):
    """
    Schema for user registration payload.
    
    Attributes:
        username (str): Unique username.
        password (str): Password (min 6 characters).
    """
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    password: str = Field(..., min_length=6, description="Password (min 6 characters)")


class UserLogin(BaseModel):
    """
    Schema for user login credentials.
    
    Attributes:
        username (str): The username of the user trying to log in.
        password (str): The password of the user trying to log in.
    """
    username: str
    password: str


class UserResponse(BaseModel):
    """
    Schema for user response data.
    
    Attributes:
        id (int): The unique identifier of the user.
        username (str): The username of the user.
    """
    id: int
    username: str
    role: str = "user"

    model_config = {
        "from_attributes": True
    }
