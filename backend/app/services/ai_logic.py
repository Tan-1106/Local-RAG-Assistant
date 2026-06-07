import torch
import nest_asyncio
from app.config                             import settings
from llama_index.llms.ollama                import Ollama
from llama_index.core                       import Settings as LlamaIndexSettings
from llama_index.embeddings.huggingface     import HuggingFaceEmbedding
from app.logger                               import get_logger

logger = get_logger(__name__)


def initialize_ai():
    """
    Initialize AI components (LLM, Embeddings, Vector Store) when FastAPI starts.
    Configures Ollama LLM and HuggingFace Embedding model. Also patches
    a known position_ids buffer corruption issue in SentenceTransformers.
    """
    logger.info("🚀 [AI Logic] Starting AI System initialization...")
    nest_asyncio.apply()

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
    logger.info(f"✅ [AI Logic] Connected to LLM: {settings.OLLAMA_MODEL}")

    # 2. Embedding Model Configuration
    device = "cuda" if torch.cuda.is_available() else "cpu"
    LlamaIndexSettings.embed_model = HuggingFaceEmbedding(
        model_name=settings.EMBEDDING_MODEL,
        device=device,
        trust_remote_code=True
    )
    
    # Patch position_ids buffer corruption issue due to transformers>=5.0 meta-device loading
    try:
        st_model = LlamaIndexSettings.embed_model._model
        # SentenceTransformer wraps the HF Transformer module at index 0 or via _first_module()
        transformer_module = st_model._first_module() if hasattr(st_model, "_first_module") else st_model[0]
        hf_model = transformer_module.auto_model
        
        if hasattr(hf_model, "embeddings") and hasattr(hf_model.embeddings, "position_ids"):
            embeddings = hf_model.embeddings
            max_positions = embeddings.position_ids.size(0)
            embeddings.register_buffer(
                "position_ids",
                torch.arange(max_positions, device=embeddings.position_ids.device),
                persistent=False
            )
            logger.info("🚀 [AI Logic] Successfully patched embedding model position_ids buffer.")
    except Exception as e:
        logger.warning(f"⚠️ [AI Logic] Failed to patch position_ids: {e}")
        
    logger.info(f"✅ [AI Logic] Loaded Embedding Model: {settings.EMBEDDING_MODEL} (Running on: {device.upper()})")
    logger.info("==================================================")