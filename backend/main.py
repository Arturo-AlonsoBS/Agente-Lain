"""
Backend de "Pregúntale a Lain".
Endpoints:
  GET  /health          -> estado del servidor
  POST /upload          -> subir un PDF o CSV para indexar
  GET  /documents        -> listar documentos cargados
  POST /ask              -> hacer una pregunta (RAG + Gemini)
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional

from config import settings
from loader import init_store, get_store
from gemini_client import init_client, get_client

ALLOWED_EXTENSIONS = {".pdf", ".csv"}
MAX_FILE_SIZE_MB = 20


# ---------- Ciclo de vida ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Iniciando a Lain...")
    init_store()
    init_client()
    print("Lain lista para recibir preguntas")
    yield
    print("Cerrando a Lain...")


app = FastAPI(title=settings.api_title, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False ,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Schemas

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    previous_interaction_id: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    sources: List[str]
    interaction_id: Optional[str] = None


class DocumentInfo(BaseModel):
    name: str
    chunks: int
    type: str


# Endpoints

@app.get("/health")
async def health():
    store = get_store()
    return {
        "status": "ok",
        "model": settings.llm_model,
        "documents_loaded": list(store.loaded_docs.keys()),
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Solo se aceptan archivos .pdf o .csv")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"El archivo supera los {MAX_FILE_SIZE_MB}MB")

    safe_name = os.path.basename(file.filename)
    save_path = os.path.join(settings.docs_path, safe_name)

    with open(save_path, "wb") as f:
        f.write(content)

    try:
        store = get_store()
        chunks = store.load_file(save_path)
    except Exception as e:
        raise HTTPException(500, f"Error al procesar el archivo: {e}")

    return {
        "status": "ok",
        "filename": safe_name,
        "chunks": chunks,
        "size_kb": round(len(content) / 1024, 1),
    }


@app.get("/documents", response_model=List[DocumentInfo])
async def documents():
    store = get_store()
    return [
        DocumentInfo(name=name, chunks=info["chunks"], type=info["type"])
        for name, info in store.loaded_docs.items()
    ]


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    store = get_store()
    client = get_client()

    question = request.question.strip()
    if not question:
        raise HTTPException(400, "La pregunta no puede estar vacía")

    # 1. Contexto: documento completo si es chico, RAG por chunks si es grande
    context, sources = store.build_context(question, k=settings.top_k)

    # 2. Generar respuesta con Gemini
    try:
        result = client.ask(
            question=question,
            context=context,
            previous_interaction_id=request.previous_interaction_id,
        )
    except Exception as e:
        raise HTTPException(500, f"Error llamando a Gemini: {e}")

    return AskResponse(
        answer=result["answer"],
        sources=sources,
        interaction_id=result["interaction_id"],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)