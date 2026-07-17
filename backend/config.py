"""
Configuración centralizada. Lee variables desde .env
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    #Gemini
    gemini_api_key: str = ""
    llm_model: str = "gemini-3.5-flash"

    # RAG
    chroma_persist_dir: str = "./data/chroma_db"
    docs_path: str = "./data/docs"
    chunk_size: int = 800
    chunk_overlap: int = 150
    top_k: int = 4

    # API
    api_title: str = "Pregúntale a Lain"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = ["*"] 

    class Config:
        env_file = ".env"
        case_sensitive = False

    def validate_required(self):
        if not self.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY no está configurada. Editá el archivo .env"
            )
        print("Config cargada correctamente")


settings = Settings()
settings.validate_required()
