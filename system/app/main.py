
"""
Entry point aplikasi FastAPI - IT Helpdesk Assistant.

Menghubungkan:
- RAG
- Tool Calling
- Intelligent Router
"""

import asyncio
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.router import handle_query
from app.rag import build_index


# Logging aplikasi
logger = logging.getLogger(__name__)


# Menyiapkan FAISS saat aplikasi dimulai
@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Membangun FAISS index...")

    try:
        index_info = await asyncio.to_thread(build_index)

        app.state.rag_index_info = index_info

        logger.info(
            "FAISS index berhasil dibangun: %s",
            index_info
        )

    except Exception:
        logger.exception(
            "Gagal membangun FAISS index saat startup."
        )
        raise

    yield

    logger.info("IT Helpdesk Assistant dihentikan.")


# Membuat aplikasi FastAPI
app = FastAPI(
    title="IT Helpdesk Assistant API",
    description=(
        "AI Helpdesk Assistant menggunakan RAG, "
        "FAISS, Gemini, dan Tool Calling."
    ),
    version="1.0.0",
    lifespan=lifespan
)


# Request schema
class AskRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        description="Pertanyaan atau permintaan pengguna."
    )


# Response schema
class AskResponse(BaseModel):
    status: str
    intent: str
    data: str


# Health check endpoint
@app.get("/health")
async def health():

    index_info = getattr(
        app.state,
        "rag_index_info",
        {}
    )

    return {
        "status": "ok",
        "rag_index_loaded": bool(index_info),
        "total_documents": index_info.get(
            "total_documents", 0
        )
    }


# Main AI endpoint
@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):

    query = request.query.strip()

    # Validasi input
    if not query:
        return AskResponse(
            status="error",
            intent="unknown",
            data="Pertanyaan tidak boleh kosong."
        )

    try:

        # Meneruskan query ke Intelligent Router
        result = await handle_query(query)

        # Mengembalikan response terstruktur
        return AskResponse(**result)

    except Exception:

        # Mencatat detail error di terminal
        logger.exception(
            "Terjadi kesalahan ketika memproses query."
        )

        # Tidak membocorkan detail internal kepada pengguna
        return AskResponse(
            status="error",
            intent="unknown",
            data=(
                "Maaf, terjadi gangguan ketika "
                "memproses permintaan Anda. "
                "Silakan coba kembali."
            )
        )
