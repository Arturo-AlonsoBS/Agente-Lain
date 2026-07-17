"""
Configuración centralizada. Lee variables desde .env
"""
import os
from pydantic_settings import BaseSettings
from typing import List
IS_RENDER = "RENDER" in os.environ

class Settings(BaseSettings):
    # Gemini
    gemini_api_key: str = ""
    llm_model: str = "gemma-4-31b-it"

    # RAG
    chroma_persist_dir: str = "/tmp/chroma_db" if IS_RENDER else "./data/chroma_db"
    docs_path: str = "/tmp/docs" if IS_RENDER else "./data/docs"
    chunk_size: int = 800
    chunk_overlap: int = 150
    top_k: int = 8


    # cantidad máxima de tokens que se mandan a Gemini en cada pregunta (RAG)
    llm_max_output_tokens: int = 3000

    # Máximo de caracteres que se mandan a Gemini en modo "contexto completo"
    full_context_char_limit: int = 60000

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
# para asegurar que las carpetas temporales existan al iniciar en Render
if IS_RENDER:
    os.makedirs(settings.chroma_persist_dir, exist_ok=True)
    os.makedirs(settings.docs_path, exist_ok=True)
settings.validate_required()