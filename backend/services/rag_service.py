import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from providers.embedding import create_embeddings
from providers.vector_store import create_vector_store
from providers.llm import create_llm

RAG_SYSTEM_PROMPT = (
    "你是一个知识库问答助手。请根据以下参考资料回答用户的问题。"
    "如果资料中没有相关信息，请如实说明，不要编造答案。"
)

RAG_USER_TEMPLATE = """参考资料：
{context}

用户问题：{question}

请根据以上参考资料回答问题："""


class RAGService:

    @staticmethod
    async def query(
        db: AsyncSession, kb_id: str, query: str, top_k: int = 5,
    ) -> dict:
        embeddings = create_embeddings()
        llm = create_llm()

        # 向量检索
        try:
            vectorstore = create_vector_store(kb_id, embeddings)
            docs_with_scores = await asyncio.to_thread(
                vectorstore.similarity_search_with_score, query, k=top_k,
            )
        except Exception:
            docs_with_scores = []

        if not docs_with_scores:
            return {
                "query": query,
                "answer": "在知识库中未找到相关内容。",
                "chunks": [],
            }

        # 构建上下文
        chunks_result = []
        for doc, score in docs_with_scores:
            chunks_result.append({
                "file_id": doc.metadata.get("file_id", ""),
                "file_name": doc.metadata.get("file_name", ""),
                "text": doc.page_content[:500],
                "score": round(1 - float(score), 4),  # cosine distance → similarity
            })

        # LLM 生成回答
        context_text = "\n\n".join(doc.page_content for doc, _ in docs_with_scores)
        prompt = RAG_USER_TEMPLATE.format(context=context_text, question=query)

        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content=RAG_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        response = await llm.ainvoke(messages)

        return {
            "query": query,
            "answer": response.content,
            "chunks": chunks_result,
        }
