"""Manual local RAG smoke test."""


def main():
    from llama_index.core.chat_engine import ContextChatEngine

    from app.services.ai_logic import initialize_ai
    from app.services.rag_pipeline import get_index

    initialize_ai()
    retriever = get_index().as_retriever(similarity_top_k=12)
    chat_engine = ContextChatEngine.from_defaults(retriever=retriever)
    response = chat_engine.chat("Kinh doanh bất động sản là gì?")
    print(response.response)


if __name__ == "__main__":
    main()
