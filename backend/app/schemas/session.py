import json
from datetime   import datetime
from typing     import List, Dict, Any, Optional
from pydantic   import BaseModel, model_validator

class SessionCreate(BaseModel):
    """
    Schema for creating a new session.
    
    Attributes:
        title (Optional[str]): The title of the session. Defaults to "Cuộc trò chuyện mới".
    """
    title: Optional[str] = "Cuộc trò chuyện mới"


class SessionUpdate(BaseModel):
    """
    Schema for updating a session.
    
    Attributes:
        title (str): The new title for the session.
    """
    title: str


class SessionResponse(BaseModel):
    """
    Schema for session response data.
    
    Attributes:
        id (str): The unique identifier of the session.
        title (str): The title of the session.
        created_at (datetime): The timestamp when the session was created.
    """
    id: str
    title: str
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class MessageResponse(BaseModel):
    """
    Schema for message response data.
    
    Attributes:
        id (int): The unique identifier of the message.
        role (str): The role of the user who sent the message.
        content (str): The content of the message.
        sources (Optional[List[Dict[str, Any]]]): A list of reference source nodes.
        created_at (datetime): The timestamp when the message was created.
    """
    id: int
    role: str
    content: str
    sources: Optional[List[Dict[str, Any]]] = None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def parse_sources(cls, data: Any) -> Any:
        """
        Parses the JSON string 'sources' field from the database model into a Python list.

        Args:
            data (Any): The incoming data, either a dictionary or a SQLAlchemy model instance.

        Returns:
            Any: The parsed dictionary payload to be validated by Pydantic.
        """
        # If it's already a dictionary
        if isinstance(data, dict):
            sources_val = data.get("sources")
            if isinstance(sources_val, str) and sources_val:
                try:
                    data["sources"] = json.loads(sources_val)
                except Exception:
                    data["sources"] = []
            return data
        
        # If it's a SQLAlchemy model, extract attributes and parse sources
        sources_str = getattr(data, "sources", None)
        sources_list = []
        if isinstance(sources_str, str) and sources_str:
            try:
                sources_list = json.loads(sources_str)
            except Exception:
                pass
                
        # Return a dictionary that Pydantic will bind
        return {
            "id": getattr(data, "id"),
            "role": getattr(data, "role"),
            "content": getattr(data, "content"),
            "created_at": getattr(data, "created_at"),
            "sources": sources_list
        }

    model_config = {
        "from_attributes": True
    }
