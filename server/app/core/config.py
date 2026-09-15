from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Enterprise RAG Knowledge Base"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"

    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1

    SECRET_KEY: str = "please-change-this-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"
    DB_NAME: str = "enterprise_rag"
    DB_CHARSET: str = "utf8mb4"

    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"
    EMBEDDING_DEVICE: str = "cpu"
    # 独立的 Embedding 端点；默认走 LLM_BASE_URL（兼容 DashScope OpenAI 兼容多模型统一前缀），
    # 若平台不共享同一 base_url（例如 DeepSeek Chat + DashScope Embedding），可单独覆盖
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_API_KEY: str = ""

    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "qwen-plus"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 8192

    # 视觉模型（图片入库链路）：上传图片时由多模态模型做 OCR + 图像理解，
    # 把图片内容转成结构化文本，再走与普通文档相同的 切片→Embedding→Chroma 检索链路。
    # 默认走 DashScope compatible-mode（qwen-vl-max）；Key 留空时回退复用 EMBEDDING_API_KEY。
    VISION_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    VISION_API_KEY: str = ""
    VISION_MODEL: str = "qwen-vl-max"  # 可选 qwen-vl-plus（更快更省，质量略低）
    VISION_TIMEOUT: float = 120.0
    VISION_IMAGE_MAX_SIDE: int = 2048  # 超过该边长的图片先等比缩小再送视觉模型
    VISION_JPEG_QUALITY: int = 90

    VECTOR_DB_PATH: str = "./data/chroma"

    UPLOAD_DIR: str = "./data/uploads"
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50

    RETRIEVAL_TOP_K: int = 6
    # 向量相似度阈值：真 Embedding（BGE/DashScope/OpenAI/text-embedding-v3 等）的本地 MVP 默认 0.35，
    # 能覆盖"这份文档讲了什么"等泛 query；向量模型不可用时直接报错提示，不存在假向量降级路径。
    # 生产环境可根据召回质量上提到 0.45~0.55。
    SIMILARITY_THRESHOLD: float = 0.35

    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset={self.DB_CHARSET}"
        )

    @property
    def CORS_ORIGINS_LIST(self) -> "List[str]":
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


settings = Settings()
