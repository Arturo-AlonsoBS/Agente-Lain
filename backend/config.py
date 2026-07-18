"""
Configuración centralizada. Lee variables desde .env
"""
import os
import tempfile
from pydantic_settings import BaseSettings
from typing import List

def _writable_tmp_dir() -> str | None:
    """Retorna un directorio temporal escribible para este entorno."""
    if os.name == "nt":
        return None
    tmp_dir = os.getenv("CHROMA_TMP_DIR") or os.getenv("TMPDIR") or tempfile.gettempdir()
    if tmp_dir and os.path.isdir(tmp_dir) and os.access(tmp_dir, os.W_OK | os.X_OK):
        return os.path.abspath(tmp_dir)
    fallback = "/tmp"
    if os.path.isdir(fallback) and os.access(fallback, os.W_OK | os.X_OK):
        return os.path.abspath(fallback)
    return None


def _default_dir(env_var: str, fallback: str) -> str:
    explicit = os.getenv(env_var)
    if explicit:
        return os.path.abspath(explicit)

    tmp_dir = _writable_tmp_dir()
    if tmp_dir is not None:
        return os.path.abspath(os.path.join(tmp_dir, fallback))

    return os.path.abspath(os.path.join(".", "data", fallback))


class Settings(BaseSettings):
    # Gemini
    gemini_api_key: str = ""
    llm_model: str = "gemma-4-31b-it"

    # RAG
    docs_path: str = _default_dir("DOCS_PATH", "docs")
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
print(f"Using docs_path={settings.docs_path}")
try:
    os.makedirs(settings.docs_path, exist_ok=True)
except Exception as e:
    print(f"Warning creando directorios de persistencia: {e}")
settings.validate_required()