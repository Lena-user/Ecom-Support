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

    # Gemini models — kiến trúc tách riêng 2 tier (classification vs RAG response)
    # để có thể đổi độc lập qua .env; hiện đội dự án chọn dùng chung 1 model cho cả 2.
    gemini_model_fast: str = "gemini-3.5-flash"    # Classification/routing (nhanh, rẻ)
    gemini_model_quality: str = "gemini-3.5-flash"  # RAG response (chất lượng)

    # Auth — đổi jwt_secret qua .env khi triển khai thật, default chỉ dùng cho dev
    jwt_secret: str = "dev-only-insecure-secret-change-me"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
