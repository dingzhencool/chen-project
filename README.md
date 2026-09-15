# 企业级 RAG 知识库系统 (MVP)

基于 **FastAPI + Vue 3 + Vite + Element Plus + Pinia + MySQL + Chroma** 的企业级检索增强生成（RAG）智能知识库系统 MVP 版本。

> 该项目参考了 GitHub 上 RAGFlow / FastGPT / MaxKB 等成熟项目的架构，采用**前后端完全物理隔离**的工程结构，方便后续容器化、CI/CD 分层部署与独立迭代。

---

## ✨ MVP 功能范围

- 🔐 **用户体系**：注册 / 登录 / JWT 鉴权 / 个人中心 / 密码修改
- 📚 **知识库管理**：知识库 CRUD、配置（TopK / 相似度阈值 / 分块大小 / 重叠 / 是否公开）
- 📄 **文档管理**：上传 PDF/DOCX/TXT/MD、文件列表、删除、处理状态展示
- 💬 **智能对话**：多会话管理、关联知识库、SSE 流式问答、引用来源展示
- 🧩 **RAG 管线占位**：`server/app/rag/` 下预留八大核心模块，后续按阶段实现

---

## 📁 项目目录

```
mianshi1/
├── server/                         # FastAPI 后端
│   ├── app/
│   │   ├── main.py                 # 应用入口（CORS、异常、路由注册）
│   │   ├── core/                   # 配置 / 数据库 / 安全 / 全局异常
│   │   ├── api/
│   │   │   ├── v1/                 # v1 路由聚合 + endpoints
│   │   │   └── deps/               # 依赖注入（当前用户 / DB Session）
│   │   ├── models/                 # SQLAlchemy ORM 模型（User/KB/Doc/Conv）
│   │   ├── schemas/                # Pydantic 模式（请求 + 响应 + 统一分页）
│   │   ├── crud/                   # 数据访问层（CRUDBase + 四个领域 CRUD）
│   │   ├── services/               # 业务层（user/kb/document/chat）
│   │   ├── rag/                    # RAG 核心管线（占位 & 接口说明）
│   │   └── utils/                  # 工具函数占位
│   ├── data/                       # uploads / chroma / sqlite 等运行时数据
│   ├── requirements.txt
│   ├── .env.example
│   ├── Dockerfile
│   └── run.py                      # 启动入口（uvicorn）
│
├── web/                            # Vue 3 + Vite + Element Plus 前端
│   ├── src/
│   │   ├── api/                    # axios API 封装（auth/kb/document/chat）
│   │   ├── components/             # layout / common / chat
│   │   ├── views/                  # auth / kb / chat / user / 404
│   │   ├── stores/                 # Pinia 状态（user/chat/knowledgeBase）
│   │   ├── router/                 # vue-router + 鉴权 beforeEach
│   │   ├── utils/                  # axios request 封装
│   │   ├── assets/styles/          # 主题变量 + 滚动条
│   │   ├── App.vue
│   │   └── main.js
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js              # Element Plus 按需引入 + API 代理
│   ├── .env.example
│   ├── nginx.conf                  # 生产静态资源托管 + 反向代理
│   └── Dockerfile
│
├── docker-compose.yml              # 一键编排：mysql / redis / server / web
└── .gitignore
```

---

## 🧱 架构分层

| 层级 | 后端模块 | 职责 |
|------|----------|------|
| 接口层 | `app/api/*` | APIRouter、请求参数校验、依赖注入、统一响应包装 |
| 业务层 | `app/services/*` | 业务校验、领域聚合、流程编排、对外返回 Tuple[data, msg] |
| 数据层 | `app/crud/*` + `app/models/*` | ORM 查询、通用 CRUD、分页/搜索 |
| 配置层 | `app/core/*` | settings (pydantic-settings)、DB Engine、安全、全局异常 |
| RAG 管线 | `app/rag/*` | 文档解析 → 分块 → Embedding → 向量库 → 检索 → LLM → 流式生成 |

后端所有模块均使用 `from app.xxx import yyy` 的**绝对导入**，避免相对导入的路径漂移。

---

## 🚀 本地启动

> 本文档仅提供入口与环境变量说明，**依赖安装命令请参考各目录内的配置文件自行执行**。

### 1. 启动依赖

- **MySQL 8.x**：需要创建数据库 `enterprise_rag`（后端启动时会自动建表）
- **Redis 7.x**（MVP 阶段可选，接口已预留）
- **Python 3.10+** / **Node 18+**

### 2. 后端

```
server/
├── 复制 .env.example 为 .env，按实际修改 SECRET_KEY / DB_* / LLM_*
└── 入口：python run.py     # 默认 0.0.0.0:8000
```

启动后访问 `http://localhost:8000/docs` 查看 OpenAPI 文档。

### 3. 前端

```
web/
├── 复制 .env.example 为 .env.local
└── 入口：vite             # 默认 http://localhost:5173，已代理 /api → :8000
```

### 4. 一键 Docker 编排

在项目根目录：

```bash
docker compose up -d --build
# 访问：
#   前端: http://localhost:5173
#   后端文档: http://localhost:8000/docs
```

---

## 🧪 下一步：RAG 管线实现路线

| 阶段 | 模块 | 要点 |
|------|------|------|
| 1 | `rag/document_parser.py` | PyMuPDF + python-docx + unstructured，提取纯文本 + 表格 |
| 2 | `rag/text_chunker.py` | 标题层级分块 + 递归字符分块 + Parent-Child 父子分块 |
| 3 | `rag/embedding.py` + `vector_store.py` | BGE 中文嵌入 + Chroma 持久化，按 kb_id 隔离 collection |
| 4 | `rag/retriever.py` | 向量稠密检索 + BM25 稀疏 → RRF 融合 → Cross-Encoder 重排序 |
| 5 | `rag/llm_client.py` + `prompt_templates.py` | OpenAI 兼容 SSE 流式 + 查询改写 / 问答 / 引用标注 Prompt |
| 6 | `rag/pipeline.py` | 串联端到端管线，替换 `services/chat_service.py` 中占位的模拟回答 |

---

## 📝 备注

- 所有敏感信息（密钥/密码）均从 `.env` 读取，代码无任何硬编码明文。
- 后端异常统一走 `BizException` + 全局处理器，前端 Axios 响应拦截器会统一处理 `code != 0`、`401` 等场景。
- 对话流式接口使用标准 `text/event-stream`，前端通过 `fetch + ReadableStream` 分块解析。
