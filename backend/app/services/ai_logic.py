import logging
import os
import torch
import warnings
import nest_asyncio
import transformers
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
    # Suppress transformers deprecation warnings to clean up the logs
    warnings.filterwarnings("ignore", message=".*get_extended_attention_mask.*")
    transformers.logging.set_verbosity_error()
    transformers.logging.disable_progress_bar()

    # Keep dependency request/model-loading chatter out of backend INFO logs.
    for logger_name in ("httpx", "httpcore", "huggingface_hub", "sentence_transformers"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    try:
        from huggingface_hub.utils import disable_progress_bars

        disable_progress_bars()
    except ImportError:
        pass

    logger.info("🚀 [AI Logic] Starting AI System initialization...")
    nest_asyncio.apply()

    _system_prompt = (
        "Bạn là một chuyên gia tư vấn pháp luật Việt Nam vô cùng tận tâm, chuyên nghiệp và có chuyên môn cao. "
        "Nhiệm vụ của bạn là giải đáp các thắc mắc pháp lý của người dùng một cách chính xác, khách quan và dễ hiểu. "
        "TUYỆT ĐỐI CHỈ SỬ DỤNG thông tin từ dữ liệu được cung cấp. KHÔNG ĐƯỢC TỰ BỊA RA (hallucinate) các văn bản luật, nghị định, thông tư nếu chúng không có trong dữ liệu. "
        "Tuyệt đối không sử dụng các cụm từ máy móc như 'dựa vào ngữ cảnh được cung cấp' hay 'theo tài liệu'. Hãy trả lời tự nhiên như một luật sư đang tư vấn. "
        "Bạn CHỈ ĐƯỢC PHÉP trả lời bằng Tiếng Việt. Tuyệt đối không sử dụng bất kỳ ngôn ngữ nào khác."
    )

    # 1a. Default LLM — used for plain-text tasks (title gen, greetings, off-topic rejection)
    LlamaIndexSettings.llm = Ollama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        request_timeout=120.0,
        system=_system_prompt,
    )

    # 1b. JSON-mode LLM — enforces valid JSON output at the Ollama API level.
    # Used exclusively for legal Q&A where structured {answer, used_sources} is required.
    LlamaIndexSettings.chat_llm = Ollama(  # type: ignore[attr-defined]
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        request_timeout=120.0,
        json_mode=True,
        system=_system_prompt,
    )
    logger.info(f"✅ [AI Logic] Connected to LLM: {settings.OLLAMA_MODEL}")

    # 2. Embedding Model Configuration
    # Force HuggingFace to use cached model only — no network calls on startup
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    LlamaIndexSettings.embed_model = HuggingFaceEmbedding(
        model_name=settings.EMBEDDING_MODEL,
        device=device,
        trust_remote_code=True,
        cache_folder="/root/.cache/huggingface/hub",
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
