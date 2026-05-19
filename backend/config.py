from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # 服务
    HOST: str
    PORT: int

    # 数据库
    DATABASE_URL: str

    # 嵌入模型
    EMBEDDING_PROVIDER: Literal["local", "openai"]
    EMBEDDING_MODEL: str
    EMBEDDING_DIMENSION: int
    # OpenAI 嵌入（EMBEDDING_PROVIDER=openai 时使用）
    OPENAI_EMBEDDING_MODEL: str
    OPENAI_EMBEDDING_DIMENSION: int

    # 向量存储
    VECTOR_STORE_PROVIDER: Literal["chroma", "milvus"]
    CHROMA_PERSIST_DIR: str
    # Milvus（VECTOR_STORE_PROVIDER=milvus 时使用）
    MILVUS_HOST: str
    MILVUS_PORT: int

    # LLM
    LLM_PROVIDER: Literal["openai"]
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str
    LLM_MODEL: str
    LLM_MAX_TOKENS: int
    LLM_TEMPERATURE: float

    # 分块
    CHUNK_SIZE: int
    CHUNK_OVERLAP: int

    # 文件上传
    UPLOAD_DIR: str
    CHUNK_DIR: str
    MAX_FILE_SIZE: int

    class Config:
        env_file = ".env"


settings = Settings()
