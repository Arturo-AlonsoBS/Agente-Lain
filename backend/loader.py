"""
Carga documentos (PDF o CSV), seindexa en ChromaDB.
"""
import csv
import os
from pathlib import Path
from typing import List

from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from pypdf import PdfReader
from sklearn.feature_extraction.text import HashingVectorizer

from config import settings


class LocalHashingEmbeddings:
    """Embeddings locales livianos para evitar dependencias de modelos externos."""

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

        self.vectorstore = Chroma(
            persist_directory=settings.chroma_persist_dir,
            embedding_function=self.embeddings,
            collection_name="lain_documents",
        )

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        self.loaded_docs = {} 
        print("DocumentStore listo")

    # Carg

    def _load_pdf(self, path: str) -> List[Document]:
        reader = PdfReader(path)
        docs: List[Document] = []

        for page_number, page in enumerate(reader.pages, start=1):
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
        """Carga un archivo (PDF o CSV) y lo indexa."""
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
        try:
            # Obtiene todos los IDs de la colección y los elimina
            all_ids = self.vectorstore.get()["ids"]
            if all_ids:
                self.vectorstore.delete(ids=all_ids)
        except Exception as e:
            print(f"Advertencia al limpiar la base de datos: {e}")
        self.loaded_docs.clear()
        try:
            for f in Path(settings.docs_path).glob("*"):
                if f.is_file() and f.name != name:
                    f.unlink()
        except Exception as e:
            print(f"Error al limpiar directorio físico: {e}")
        self.vectorstore.add_documents(chunks)
        self.vectorstore.persist()
        
        self.loaded_docs[name] = {"chunks": len(chunks), "type": doc_type}
        print(f"{name} indexado ({len(chunks)} chunks, tipo {doc_type})")
        return len(chunks)

    def load_all_from_docs_dir(self):
        """Carga todos los PDF/CSV que ya estén en data/docs al iniciar el servidor."""
        files = list(Path(settings.docs_path).glob("*.pdf")) + list(
            Path(settings.docs_path).glob("*.csv")
        )
        if not files:
            print(f"No hay documentos en {settings.docs_path}. Subí uno con /upload.")
            return
        for f in files:
            try:
                self.load_file(str(f))
            except Exception as e:
                print(f"Error cargando {f.name}: {e}")

    # Busqueda

    def search(self, query: str, k: int = None) -> List[Document]:
        k = k or settings.top_k
        if not self.loaded_docs:
            return []
        return self.vectorstore.similarity_search(query, k=k)

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
