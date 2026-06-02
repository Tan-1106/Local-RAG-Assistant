import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, model_validator

class SessionCreate(BaseModel):
    title: Optional[str] = "Cuộc trò chuyện mới"


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    sources: Optional[List[Dict[str, Any]]] = None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def parse_sources(cls, data: Any) -> Any:
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
