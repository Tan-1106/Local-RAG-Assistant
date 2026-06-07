from pydantic   import BaseModel
from typing     import List, Dict, Any

class ChatRequest(BaseModel):
    """
    Schema for incoming chat query.
    
    Attributes:
        question (str): The legal question or query to be processed by the RAG pipeline.
    """
    question: str

class SourceNode(BaseModel):
    """
    Schema for reference source node.
    
    Attributes:
        score (float): The relevance score of the source node.
        text (str): The content of the source node.
        metadata (Dict[str, Any]): Additional metadata associated with the source node.
    """
    score: float
    text: str
    metadata: Dict[str, Any]

class ChatResponse(BaseModel):
    """
    Schema for outgoing chat response.
    
    Attributes:
        answer (str): The response to the legal question.
        sources (List[SourceNode]): A list of reference source nodes.
    """
    answer: str
    sources: List[SourceNode]
