# MiniRAG 后端技术架构文档

## 1. 总体架构

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (Vue 3)                  │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP /api/*
┌──────────────────────▼──────────────────────────────┐
│                  FastAPI 路由层                       │
│  ┌──────────┬──────────┬──────────┬───────────────┐ │
│  │ KB CRUD  │ 文件上传  │ 文件管理  │  RAG 查询     │ │
│  └────┬─────┴────┬─────┴────┬─────┴──────┬────────┘ │
│       │          │          │            │           │
│  ┌────▼──────────▼──────────▼────────────▼────────┐ │
│  │              Service 业务层                      │ │
│  │  KBService │ FileService │ EmbeddingService │   │ │
│  └────┬──────────┬──────────────┬───────────────┘   │
│       │          │              │                    │
│  ┌────▼──────────▼──────────────▼───────────────┐   │
│  │              基础设施层                         │   │
│  │  SQLite  │ 文件系统  │ Embedding模型 │ LLM     │   │
│  └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**核心流程**：

1. **上传流程**：文件分片上传 → 合并 → 文档解析 → 文本分块 → 向量嵌入 → 存入向量库
2. **查询流程**：用户问题 → 向量嵌入 → 相似度检索 → Top-K 文档片段 → LLM 生成回答

---

## 2. 技术选型

| 组件 | 技术 | 版本 | 说明 |
|------|------|------|------|
| Web 框架 | FastAPI | >=0.100 | 异步、自动文档、类型校验 |
| ASGI 服务器 | Uvicorn | >=0.23 | 高性能异步服务器 |
| 数据库 | SQLite (aiosqlite) | >=0.19 | 轻量、零配置、单文件持久化 |
| ORM | SQLAlchemy 2.0 | >=2.0 | 异步 ORM，声明式模型 |
| 文档解析 | python-docx / PyPDF2 | latest | 支持 .txt / .md / .pdf / .docx |
| 文本分块 | langchain-text-splitters | >=0.3 | 递归字符分块，支持中英文 |
| 向量嵌入 | sentence-transformers | latest | 嵌入模型加载与推理工具库 |
| 嵌入模型 | bge-small-zh-v1.5 | — | 中文语义向量，512 维，轻量本地模型 |
| 向量存储 | ChromaDB | >=0.4 | 本地嵌入式向量数据库 |
| LLM | OpenAI 兼容接口 | — | 支持 OpenAI / 本地 Ollama 等 |
| 配置管理 | pydantic-settings | >=2.0 | .env 文件 + 类型安全的配置 |
| 文件上传 | python-multipart | >=0.0.6 | 分片上传支持 |

### 选型理由

- **SQLite**：单机部署无需数据库服务，适合中小规模知识库（<10万文档片段）
- **ChromaDB**：嵌入式向量数据库，无需独立服务，Python 原生，与 FastAPI 同进程
- **bge-small-zh-v1.5**：BAAI 开源中文向量模型，512 token 上下文，CPU 可跑，质量和速度平衡好
- **sentence-transformers**：Hugging Face 生态，模型加载和推理统一接口
- **langchain-text-splitters**：仅引入分块工具，不依赖完整 langchain 框架，避免过重依赖
- **OpenAI 兼容接口**：通过 `OPENAI_BASE_URL` 配置，支持 OpenAI、Azure、Ollama 等多种后端

---

## 3. 目录结构

```
backend/
├── server.py               # 入口：创建 app、注册路由、启动服务
├── config.py               # 配置管理（pydantic-settings，读取 .env）
├── database.py             # 数据库引擎、会话管理、表初始化
├── models.py               # SQLAlchemy ORM 模型（KB、File、Chunk）
├── schemas.py              # Pydantic 请求/响应模型
├── requirements.txt        # Python 依赖
├── .env.example            # 环境变量示例
│
├── routers/                # 路由模块
│   ├── __init__.py
│   ├── kb.py               # 知识库 CRUD 接口
│   ├── files.py            # 文件上传与管理接口
│   └── query.py            # RAG 查询接口
│
├── services/               # 业务逻辑层
│   ├── __init__.py
│   ├── kb_service.py       # 知识库业务逻辑
│   ├── file_service.py     # 文件上传、合并、管理
│   ├── embedding_service.py # 向量嵌入（模型加载、文本向量化）
│   ├── retrieval_service.py # 向量检索（相似度搜索）
│   └── llm_service.py      # LLM 调用（回答生成）
│
├── core/                   # 核心处理模块
│   ├── __init__.py
│   ├── parser.py           # 文档解析（txt/md/pdf/docx）
│   ├── chunker.py          # 文本分块（递归字符分割）
│   └── vector_store.py     # ChromaDB 向量存储封装
│
├── uploads/                # 上传文件存储（gitignore）
├── chunks/                 # 临时分片（gitignore）
└── data/                   # 持久化数据（gitignore）
    ├── minirag.db          # SQLite 数据库文件
    └── chroma/             # ChromaDB 持久化目录
```

---

## 4. 核心模块设计

### 4.1 配置管理 (`config.py`)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 服务
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 数据库
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/minirag.db"

    # 向量存储
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"
    EMBEDDING_DIMENSION: int = 512

    # LLM
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.3

    # 分块
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50

    # 文件上传
    UPLOAD_DIR: str = "./uploads"
    CHUNK_DIR: str = "./chunks"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB

    class Config:
        env_file = ".env"

settings = Settings()
```

### 4.2 数据模型 (`models.py`)

```
KnowledgeBase          File                Chunk
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ id    (PK)   │──┐│ id    (PK)   │──┐│ id    (PK)   │
│ name         │  └│ kb_id  (FK)  │  └│ file_id (FK) │
│ created_at   │   │ name         │   │ content      │
│ description  │   │ size         │   │ chunk_index  │
└──────────────┘   │ status       │   │ embedding_id │
                   │ path         │   │ created_at   │
                   │ created_at   │   └──────────────┘
                   └──────────────┘
```

- **KnowledgeBase**：知识库元信息
- **File**：上传文件元信息，关联所属知识库
- **Chunk**：文本分块，`embedding_id` 对应 ChromaDB 中的向量 ID
- 嵌入向量本身存储在 ChromaDB 中（不存 SQLite），通过 `embedding_id` 关联

### 4.3 文档解析 (`core/parser.py`)

| 格式 | 库 | 说明 |
|------|-----|------|
| .txt / .md | 内置 open() | 直接读取，UTF-8 |
| .pdf | PyPDF2 | 逐页提取文本 |
| .docx | python-docx | 段落级提取 |

返回统一格式：`{ filename, format, content: str, metadata: dict }`

### 4.4 文本分块 (`core/chunker.py`)

使用 `langchain-text-splitters` 的 `RecursiveCharacterTextSplitter`：

```
原文档
  │
  ├── 按段落分隔符 (\n\n) 分割
  │     ├── 块大小 <= CHUNK_SIZE (500字符) → 保留
  │     └── 块大小 > CHUNK_SIZE → 按句子/字符继续分割
  │
  └── 添加 CHUNK_OVERLAP (50字符) 重叠
        │
        └── 输出: [{ index, content, metadata }]
```

**中文优化**：分隔符优先级：`["\n\n", "。", "！", "？", ".", " "]`

### 4.5 向量嵌入 (`services/embedding_service.py`)

```
加载模型 (启动时单例)
  │
  ├── sentence-transformers 加载 EMBEDDING_MODEL
  │
  └── 提供接口:
       ├── embed_text(text) -> list[float]        # 单文本向量化
       └── embed_texts(texts) -> list[list[float]] # 批量向量化
```

- 首次运行自动从 Hugging Face 下载模型（~100MB），后续使用本地缓存
- CPU 推理，单次嵌入约 10-50ms（短文本）

### 4.6 向量存储 (`core/vector_store.py`)

封装 ChromaDB 操作：

```python
class VectorStore:
    def add_chunks(kb_id, chunks: list[dict]) -> list[str]    # 批量插入，返回 ID 列表
    def search(kb_id, query_embedding, top_k) -> list[dict]   # 相似度搜索
    def delete_by_file(file_id)                                # 按文件删除所有分块
    def delete_by_kb(kb_id)                                   # 按知识库删除所有分块
```

- 每个知识库对应一个 ChromaDB Collection
- metadata 存储 `file_id`、`chunk_index` 用于追溯来源

### 4.7 LLM 问答 (`services/llm_service.py`)

```python
class LLMService:
    def generate_answer(query: str, contexts: list[str]) -> str
```

**Prompt 模板**：

```
你是一个知识库问答助手。请根据以下参考资料回答用户的问题。
如果资料中没有相关信息，请如实说明，不要编造答案。

参考资料：
{contexts}

用户问题：{query}

回答：
```

- 使用 OpenAI SDK 调用，通过 `OPENAI_BASE_URL` 兼容各种后端
- 支持 Ollama 本地部署：`OPENAI_BASE_URL=http://localhost:11434/v1`

---

## 5. 数据持久化

### 5.1 SQLite 数据库

```sql
-- 启用时开启 WAL 模式提升并发读性能
PRAGMA journal_mode=WAL;

CREATE TABLE knowledge_bases (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE files (
    id         TEXT PRIMARY KEY,
    kb_id      TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    size       INTEGER NOT NULL,
    status     TEXT DEFAULT 'uploading',  -- uploading / processing / done / failed
    path       TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE chunks (
    id           TEXT PRIMARY KEY,
    file_id      TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    content      TEXT NOT NULL,
    chunk_index  INTEGER NOT NULL,
    embedding_id TEXT,           -- ChromaDB 中的向量 ID
    created_at   TEXT NOT NULL
);

CREATE INDEX idx_files_kb_id ON files(kb_id);
CREATE INDEX idx_chunks_file_id ON chunks(file_id);
```

### 5.2 文件系统

```
data/
├── minirag.db          # SQLite 数据库
└── chroma/             # ChromaDB 向量数据

uploads/                # 原始上传文件
└── {kb_id}/
    └── {filename}

chunks/                 # 临时分片（合并后删除）
```

### 5.3 启动时数据恢复

服务启动时：
1. 初始化 SQLite 连接，创建表（如不存在）
2. 扫描 `uploads/` 目录，将 `status=uploading` 的文件标记为 `failed`（断点续传暂不实现）
3. 加载嵌入模型到内存
4. 初始化 ChromaDB 连接

---

## 6. API 设计

保持与现有前端完全兼容，不修改任何已有接口。

### 6.1 现有接口（不变）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/kb` | 创建知识库 |
| GET | `/api/kb` | 列出所有知识库 |
| GET | `/api/kb/{kb_id}` | 获取知识库详情 |
| DELETE | `/api/kb/{kb_id}` | 删除知识库 |
| POST | `/api/upload/chunk` | 上传文件分片 |
| GET | `/api/files` | 列出所有文件 |
| DELETE | `/api/files/{file_id}` | 删除文件 |
| POST | `/api/query` | RAG 查询 |

### 6.2 核心接口行为变更

**`POST /api/upload/chunk`** — 最后一个分片上传后触发后台处理：
1. 合并分片为完整文件 → `status: done`（现有逻辑）
2. **新增**：异步触发文档处理管道
   - 解析文档 → 分块 → 向量化 → 存入 ChromaDB
   - 处理过程中 `status: processing`
   - 完成后 `status: indexed`
   - 失败则 `status: failed`

**`POST /api/query`** — 从关键词匹配升级为语义检索 + LLM 生成：
1. 将查询文本向量化
2. 在目标知识库的 ChromaDB Collection 中检索 Top-K
3. 用检索到的文档片段构建 Prompt
4. 调用 LLM 生成回答
5. 返回格式不变：`{ query, answer, chunks }`

### 6.3 新增接口（可选）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（模型加载状态等） |
| GET | `/api/kb/{kb_id}/stats` | 知识库统计（文件数、分块数） |

---

## 7. 完整文件处理管道

```
用户上传文件（前端分片）
       │
       ▼
 分片逐个到达 /api/upload/chunk
       │
       ▼ (最后一个分片)
 合并分片 → 保存原始文件
       │ status: processing
       ▼
 文档解析 (parser.py)
  ├── .txt/.md → 直接读取
  ├── .pdf → PyPDF2 提取
  └── .docx → python-docx 提取
       │
       ▼
 文本分块 (chunker.py)
  └── RecursiveCharacterTextSplitter
       │
       ▼
 向量嵌入 (embedding_service.py)
  └── bge-small-zh-v1.5 → 512维向量
       │
       ▼
 存储向量 (vector_store.py)
  └── ChromaDB (按 kb_id 分 Collection)
       │
       ▼
 更新数据库 (database.py)
  └── chunks 表 + files.status = "indexed"
```

---

## 8. 配置管理

### `.env.example`

```env
# 服务配置
HOST=0.0.0.0
PORT=8000

# 数据库
DATABASE_URL=sqlite+aiosqlite:///./data/minirag.db

# 向量存储
CHROMA_PERSIST_DIR=./data/chroma
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
EMBEDDING_DIMENSION=512

# LLM（支持 OpenAI / Ollama / Azure 等 OpenAI 兼容接口）
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_MAX_TOKENS=2048
LLM_TEMPERATURE=0.3

# 文本分块
CHUNK_SIZE=500
CHUNK_OVERLAP=50

# 文件上传
MAX_FILE_SIZE=52428800
```

### 使用 Ollama 本地部署示例

```env
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:7b
```

---

## 9. 依赖清单

```
# requirements.txt
fastapi>=0.100.0
uvicorn>=0.23.0
python-multipart>=0.0.6

# 数据库
sqlalchemy>=2.0.0
aiosqlite>=0.19.0

# 文档解析
PyPDF2>=3.0.0
python-docx>=1.0.0

# 文本分块
langchain-text-splitters>=0.3.0

# 向量嵌入与存储
sentence-transformers>=2.2.0
chromadb>=0.4.0

# LLM
openai>=1.0.0

# 配置
pydantic-settings>=2.0.0
```

---

## 10. 开发路线图

### Phase 1：基础设施（重构现有功能）
- [ ] 搭建模块化目录结构
- [ ] 实现 config.py + .env 配置
- [ ] 实现 database.py + models.py（SQLite 持久化）
- [ ] 迁移 KB CRUD 和文件上传到 routers + services
- [ ] 验证：前端所有功能正常，数据重启不丢失

### Phase 2：文档处理管道
- [ ] 实现 parser.py（txt/md/pdf/docx 解析）
- [ ] 实现 chunker.py（递归字符分块）
- [ ] 实现文件上传后的自动处理管道
- [ ] 验证：上传文件后能在数据库中看到分块记录

### Phase 3：向量检索
- [ ] 实现 embedding_service.py（模型加载与推理）
- [ ] 实现 vector_store.py（ChromaDB 封装）
- [ ] 将文档处理管道接入向量化步骤
- [ ] 验证：上传文档后能进行语义相似度搜索

### Phase 4：LLM 问答
- [ ] 实现 llm_service.py（OpenAI 兼容接口调用）
- [ ] 升级 /api/query 接口为完整的 RAG 流程
- [ ] 验证：端到端问答正常工作
