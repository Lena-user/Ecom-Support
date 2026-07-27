"""Cấu hình tập trung — đọc toàn bộ biến môi trường từ .env."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Cấu hình ứng dụng, tự đọc từ biến môi trường hoặc file .env."""

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379

    # Qdrant
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333

    # Gemini API
    gemini_api_key: str = ""

    # Gemini models — tách 2 tier theo độ phức tạp
    gemini_model_fast: str = "gemini-3.5-flash"    # Classification/routing (nhanh, rẻ)
    gemini_model_quality: str = "gemini-3.5-flash"  # RAG response (chất lượng)

    # Embedding API (dùng ở bước 4)
    openai_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
