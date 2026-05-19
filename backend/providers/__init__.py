"""Provider 工厂：基于 LangChain 的可插拔组件。"""

from providers.embedding import create_embeddings
from providers.vector_store import create_vector_store, delete_kb_collection
from providers.llm import create_llm
