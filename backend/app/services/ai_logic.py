import torch
from app.config import settings
from llama_index.llms.ollama import Ollama
from llama_index.core import Settings as LlamaIndexSettings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

def initialize_ai():
    """
    This function is called when FastAPI starts to load AI into memory.
    """
    print("🚀 [AI Logic] Starting AI System initialization...")

    # 1. LLM Configuration (Qwen2.5:7b via Ollama)
    LlamaIndexSettings.llm = Ollama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        request_timeout=120.0,
        system=(
            "Bạn là trợ lý AI chuyên gia về Luật pháp Việt Nam. "
            "Nhiệm vụ của bạn là dựa vào ngữ cảnh được cung cấp để trả lời câu hỏi một cách chính xác, khách quan. "
            "Bạn CHỈ ĐƯỢC PHÉP trả lời bằng Tiếng Việt. Tuyệt đối không sử dụng tiếng Trung hoặc bất kỳ ngôn ngữ nào khác."
        )
    )
    print(f"✅ [AI Logic] Connected to LLM: {settings.OLLAMA_MODEL}")

    # 2. Embedding Model Configuration
    device = "cuda" if torch.cuda.is_available() else "cpu"
    LlamaIndexSettings.embed_model = HuggingFaceEmbedding(
        model_name=settings.EMBEDDING_MODEL,
        device=device,
        trust_remote_code=True
    )
    print(f"✅ [AI Logic] Loaded Embedding Model: {settings.EMBEDDING_MODEL} (Running on: {device.upper()})")
    print("==================================================")