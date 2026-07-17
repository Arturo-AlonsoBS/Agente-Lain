"""
Carga documentos (PDF o CSV), se indexa en ChromaDB.

Modo híbrido de contexto:
- Si el documento (o los documentos) cargados entran dentro de
  `settings.full_context_char_limit`, se manda el TEXTO COMPLETO a Gemini.
  Esto evita que documentos cortos (resúmenes, apuntes) se "corten" a mitad
  de una sección por culpa del chunking + ranking de embeddings.
- Si el documento es grande y no entra, se usa búsqueda semántica por
  fragmentos (RAG clásico) como antes.
"""
import csv
import os
import shutil
from pathlib import Path
from typing import List, Tuple

import pdfplumber
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from sklearn.feature_extraction.text import HashingVectorizer

from config import settings


class LocalHashingEmbeddings:
    """Embeddings locales livianos para evitar dependencias de modelos externos.

    OJO: esto es una bolsa de palabras con hashing, NO embeddings semánticos
    reales. Sirve como fallback rápido para documentos grandes, pero no
    entiende sinónimos ni relaciones de significado. Para documentos chicos
    no importa porque usamos el modo de "contexto completo" (ver build_context).
    """

    def __init__(self, n_features: int = 512):
        self.vectorizer = HashingVectorizer(
            n_features=n_features,
            alternate_sign=False,
            norm="l2",
            lowercase=True,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        matrix = self.vectorizer.transform(texts)
        return matrix.toarray().tolist()

    def embed_query(self, text: str) -> List[float]:
        return self.vectorizer.transform([text]).toarray()[0].tolist()


class DocumentStore:
    """Gestiona la carga, indexado y búsqueda de documentos (PDF/CSV)."""

    def __init__(self):
        os.makedirs(settings.chroma_persist_dir, exist_ok=True)
        os.makedirs(settings.docs_path, exist_ok=True)

        print("Cargando embeddings locales livianos...")
        self.embeddings = LocalHashingEmbeddings()

        self._reset_vectorstore()

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        self.loaded_docs = {}   # nombre -> {chunks, type}
        self.full_texts = {}    # nombre -> texto completo del documento
        print("DocumentStore listo")

    def _reset_vectorstore(self):
        if os.path.exists(settings.chroma_persist_dir):
            shutil.rmtree(settings.chroma_persist_dir, ignore_errors=True)
        os.makedirs(settings.chroma_persist_dir, exist_ok=True)
        self.vectorstore = Chroma(
            persist_directory=settings.chroma_persist_dir,
            embedding_function=self.embeddings,
            collection_name="lain_documents",
        )

    # ---------- Carga ----------

    def _load_pdf(self, path: str) -> List[Document]:
        """
        Usa pdfplumber (no pypdf) porque reconstruye los espacios entre
        palabras a partir de la posición real de cada carácter en la
        página. pypdf, con PDFs generados por ciertos editores (ej. Google
        Docs exportado), puede devolver el texto completamente pegado
        ("Unatransacciónsecon..."), lo que vuelve el contexto casi
        ilegible para el modelo aunque el contenido esté completo.
        """
        docs: List[Document] = []

        with pdfplumber.open(path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if not text.strip():
                    continue

                docs.append(
                    Document(
                        page_content=text,
                        metadata={"source": path, "page": page_number},
                    )
                )

        return self.splitter.split_documents(docs)

    def _load_csv(self, path: str) -> List[Document]:
        docs: List[Document] = []

        with open(path, newline="", encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            for row_number, row in enumerate(reader, start=1):
                content = "\n".join(f"{key}: {value}" for key, value in row.items())
                docs.append(
                    Document(
                        page_content=content,
                        metadata={"source": path, "row": row_number},
                    )
                )

        return docs

    def load_file(self, path: str) -> int:
        """Carga un archivo (PDF o CSV), lo indexa y guarda su texto completo."""
        ext = Path(path).suffix.lower()
        name = Path(path).name

        if ext == ".pdf":
            chunks = self._load_pdf(path)
            doc_type = "pdf"
        elif ext == ".csv":
            chunks = self._load_csv(path)
            doc_type = "csv"
        else:
            raise ValueError(f"Formato no soportado: {ext} (solo .pdf o .csv)")

        for chunk in chunks:
            chunk.metadata["source_doc"] = name

        # Solo un documento activo a la vez: se limpia lo anterior.
        self.loaded_docs.clear()
        self.full_texts.clear()
        try:
            for f in Path(settings.docs_path).glob("*"):
                if f.is_file() and f.name != name:
                    f.unlink()
        except Exception as e:
            print(f"Error al limpiar directorio físico: {e}")

        self._reset_vectorstore()
        self.vectorstore.add_documents(chunks)
        self.vectorstore.persist()

        self.full_texts[name] = "\n\n".join(c.page_content for c in chunks)

        self.loaded_docs[name] = {"chunks": len(chunks), "type": doc_type}
        print(f"{name} indexado ({len(chunks)} chunks, tipo {doc_type})")
        return len(chunks)

    def load_all_from_docs_dir(self):
        """Carga el último PDF/CSV en data/docs al iniciar el servidor."""
        files = list(Path(settings.docs_path).glob("*.pdf")) + list(
            Path(settings.docs_path).glob("*.csv")
        )
        if not files:
            print(f"No hay documentos en {settings.docs_path}. Subí uno con /upload.")
            return

        files = sorted(files, key=lambda f: f.stat().st_mtime)
        latest_file = files[-1]

        for f in files[:-1]:
            try:
                f.unlink()
            except Exception as e:
                print(f"Error al eliminar documento antiguo {f.name}: {e}")

        try:
            self.load_file(str(latest_file))
        except Exception as e:
            print(f"Error cargando {latest_file.name}: {e}")

    # ---------- Búsqueda ----------

    def search(self, query: str, k: int = None) -> List[Document]:
        k = k or settings.top_k
        if not self.loaded_docs:
            return []
        return self.vectorstore.similarity_search(query, k=k)

    def build_context(self, query: str, k: int = None) -> Tuple[str, List[str]]:
        """
        Devuelve (contexto, fuentes) listo para mandarle a Gemini.

        - Documento(s) chico(s) (entran en full_context_char_limit):
          se manda el texto COMPLETO. Más lento/costoso por token, pero
          100% confiable: nunca se "corta" una sección a la mitad.
        - Documento grande: RAG clásico por fragmentos (similarity_search).
        """
        if not self.loaded_docs:
            return "", []

        total_chars = sum(len(t) for t in self.full_texts.values())

        if total_chars <= settings.full_context_char_limit:
            parts = [
                f"=== Documento: {name} ===\n{text}"
                for name, text in self.full_texts.items()
            ]
            return "\n\n".join(parts), list(self.full_texts.keys())

        docs = self.search(query, k=k)
        context = "\n\n---\n\n".join(
            f"[{d.metadata.get('source_doc', 'desconocido')}] {d.page_content}"
            for d in docs
        )
        sources = sorted({d.metadata.get("source_doc", "desconocido") for d in docs})
        return context, sources

    def stats(self) -> dict:
        try:
            total = len(self.vectorstore.get()["documents"])
        except Exception:
            total = 0
        return {"documents": self.loaded_docs, "total_chunks": total}


# Instancia global
_store: DocumentStore = None


def init_store() -> DocumentStore:
    global _store
    if _store is None:
        _store = DocumentStore()
        _store.load_all_from_docs_dir()
    return _store


def get_store() -> DocumentStore:
    if _store is None:
        raise RuntimeError("DocumentStore no inicializado")
    return _store