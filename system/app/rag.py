
"""
RAG IT Helpdesk Assistant
Assignment 5 - Optimasi EVAL-11

Perbaikan:
- Retrieval untuk pertanyaan multi-topik
- Jawaban lengkap untuk beberapa topik
- Batas output dinamis
- Logging untuk analisis token dan latency
"""

import os
import asyncio
import logging

import faiss
import numpy as np
import pandas as pd

from dotenv import load_dotenv, find_dotenv
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

load_dotenv(find_dotenv(usecwd=True), override=True)

_client = genai.Client(
    api_key=os.environ.get("GEMINI_API_KEY")
)

EMBEDDING_MODEL = "gemini-embedding-001"
GENERATION_MODEL = "gemini-3.6-flash"
KNOWLEDGE_BASE_PATH = "data/it_helpdesk_knowledge_base.csv"

_index = None
_documents = None
_df = None


def _get_embedding(
    text: str,
    task_type: str = "RETRIEVAL_DOCUMENT"
) -> np.ndarray:

    result = _client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=task_type
        )
    )

    return np.asarray(
        result.embeddings[0].values,
        dtype=np.float32
    )


def build_index():
    """Membangun FAISS index saat startup."""

    global _index, _documents, _df

    df = pd.read_csv(
        KNOWLEDGE_BASE_PATH
    ).fillna("")

    required = {
        "faq_id", "category", "question", "answer"
    }

    if not required.issubset(df.columns):
        raise ValueError(
            "Kolom knowledge base tidak lengkap"
        )

    documents = []
    texts = []

    for _, row in df.iterrows():

        content = (
            f"Category: {row['category']}\n"
            f"Question: {row['question']}\n"
            f"Answer: {row['answer']}"
        )

        texts.append(content)

        documents.append({
            "faq_id": str(row["faq_id"]),
            "category": str(row["category"]),
            "question": str(row["question"]),
            "answer": str(row["answer"]),
            "content": content
        })

    if not documents:
        raise ValueError("Knowledge base kosong")

    result = _client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT"
        )
    )

    vectors = np.ascontiguousarray(
        [
            item.values
            for item in result.embeddings
        ],
        dtype=np.float32
    )

    if len(vectors) != len(documents):
        raise ValueError(
            "Jumlah embedding tidak sesuai dokumen"
        )

    faiss.normalize_L2(vectors)

    index = faiss.IndexFlatIP(
        vectors.shape[1]
    )

    index.add(vectors)

    _index = index
    _documents = documents
    _df = df

    return {
        "total_documents": len(documents),
        "vector_dimension": vectors.shape[1],
        "index_type": "IndexFlatIP"
    }


def semantic_search(
    query: str,
    top_k: int = 3
):
    """Pencarian FAISS untuk pertanyaan biasa."""

    global _index, _documents

    if not isinstance(query, str) or not query.strip():
        raise ValueError("Query tidak boleh kosong")

    if top_k < 1:
        raise ValueError("top_k minimal harus 1")

    if _index is None or _documents is None:
        build_index()

    if _index.ntotal == 0:
        return []

    vector = _get_embedding(
        query.strip(),
        task_type="RETRIEVAL_QUERY"
    )

    vector = np.asarray(
        vector,
        dtype=np.float32
    ).reshape(1, -1)

    if vector.shape[1] != _index.d:
        raise ValueError(
            "Dimensi query tidak sesuai FAISS"
        )

    faiss.normalize_L2(vector)

    scores, indices = _index.search(
        vector,
        min(top_k, _index.ntotal)
    )

    results = []

    for score, idx in zip(
        scores[0], indices[0]
    ):

        if idx >= 0:
            doc = dict(
                _documents[int(idx)]
            )

            doc["score"] = float(score)
            results.append(doc)

    return results


def _requested_topics(query: str):
    """Mendeteksi topik dari pertanyaan."""

    q = query.casefold()
    topics = []

    if "cuti" in q:
        topics.append("cuti")

    if "password" in q:
        topics.append("password")

    if (
        "perangkat" in q
        or "laptop baru" in q
    ):
        topics.append("perangkat")

    if (
        "onboarding" in q
        or "karyawan baru" in q
    ):
        topics.append("onboarding")

    return topics


def _retrieve_multi_topic(query: str):
    """
    Mengambil FAQ berdasarkan topik.

    Digunakan jika pertanyaan berisi
    minimal dua topik yang dikenali.
    """

    global _documents

    topics = _requested_topics(query)

    if len(topics) < 2:
        return []

    if _documents is None:
        build_index()

    collected = []
    seen = set()

    limits = {
        "cuti": 8,
        "password": 3,
        "perangkat": 2,
        "onboarding": 3
    }

    for topic in topics:

        choices = []

        for doc in _documents:

            category = doc[
                "category"
            ].casefold()

            question = doc[
                "question"
            ].casefold()

            answer = doc[
                "answer"
            ].casefold()

            text = question + " " + answer

            if topic == "cuti":

                matched = (
                    "cuti" in text
                    or "cuti & absensi" in category
                )

                priority = (
                    2 if "cuti" in question else 1
                )

            elif topic == "password":

                matched = "password" in text

                priority = (
                    2 if "reset password" in text
                    else 1
                )

            elif topic == "perangkat":

                matched = (
                    "perangkat & equipment"
                    in category
                )

                priority = (
                    3 if (
                        "permintaan" in question
                        or "laptop baru" in question
                    ) else 1
                )

            else:

                matched = (
                    "onboarding" in text
                    or "karyawan baru" in question
                    or "hari pertama" in question
                )

                priority = (
                    2 if (
                        "hari pertama" in question
                        or "onboarding" in question
                    ) else 1
                )

            if matched:
                choices.append(
                    (priority, doc)
                )

        choices.sort(
            key=lambda item: item[0],
            reverse=True
        )

        for _, doc in choices[
            :limits[topic]
        ]:

            if doc["faq_id"] not in seen:

                collected.append(doc)

                seen.add(
                    doc["faq_id"]
                )

    return collected


async def answer_from_knowledge_base(
    query: str
) -> str:
    """
    Menghasilkan jawaban menggunakan RAG.

    Pertanyaan biasa: FAISS top_k=3
    Multi-topik: retrieval per kategori
    """

    topics = _requested_topics(query)

    is_multi_topic = len(topics) >= 2

    if is_multi_topic:

        retrieved_docs = (
            _retrieve_multi_topic(query)
        )

    else:

        retrieved_docs = semantic_search(
            query,
            top_k=3
        )

    if not retrieved_docs:

        return (
            "Maaf, informasi yang Anda cari "
            "belum ditemukan dalam "
            "knowledge base IT."
        )

    context = "\n---\n".join(

        f"FAQ ID: {doc['faq_id']}\n"
        f"Category: {doc['category']}\n"
        f"Question: {doc['question']}\n"
        f"Answer: {doc['answer']}"

        for doc in retrieved_docs
    )

    system_instruction = """
Anda adalah IT Helpdesk Assistant internal perusahaan.

Jawab hanya berdasarkan knowledge base yang diberikan.

Jangan mengarang kebijakan, prosedur, angka,
atau tindakan yang belum dilakukan.

Jika informasi tentang suatu bagian tidak tersedia,
jelaskan keterbatasannya.

Gunakan bahasa Indonesia yang jelas.

Cantumkan FAQ ID yang relevan sebagai sumber.

Jika pertanyaan memuat beberapa topik,
gunakan subjudul terpisah untuk setiap topik.

Pastikan tidak ada topik yang terlewat.
Jangan mengulangi informasi yang sama.
"""

    if is_multi_topic:

        topic_instruction = (
            "Topik yang wajib dibahas: "
            + ", ".join(topics)
            + ". Jelaskan masing-masing "
            "secara cukup rinci sesuai FAQ."
        )

    else:

        topic_instruction = (
            "Jawab secara langsung dan ringkas."
        )

    prompt = f"""
PERTANYAAN PENGGUNA:
{query}

KONTEKS KNOWLEDGE BASE:
{context}

{topic_instruction}

Jangan menambah informasi di luar konteks.
"""

    response = await asyncio.to_thread(
        _client.models.generate_content,
        model=GENERATION_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            max_output_tokens=(
                3072 if is_multi_topic
                else 1024
            )
        )
    )

    answer = (
        response.text or ""
    ).strip()

    candidates = (
        getattr(response, "candidates", None)
        or []
    )

    candidate = (
        candidates[0]
        if candidates else None
    )

    finish_reason = getattr(
        candidate,
        "finish_reason",
        "UNKNOWN"
    )

    usage = getattr(
        response,
        "usage_metadata",
        None
    )

    output_tokens = getattr(
        usage,
        "candidates_token_count",
        None
    )

   
    print(
        f"[RAG DEBUG] "
        f"Characters: {len(answer)} | "
        f"Finish reason: {finish_reason} | "
        f"FAQ count: {len(retrieved_docs)} | "
        f"Input tokens: {getattr(usage, 'prompt_token_count', None)} | "
        f"Output tokens: {getattr(usage, 'candidates_token_count', None)} | "
        f"Thinking tokens: {getattr(usage, 'thoughts_token_count', None)} | "
        f"Total tokens: {getattr(usage, 'total_token_count', None)}"
    )


    if not answer:
        raise RuntimeError(
            "Gemini tidak menghasilkan jawaban."
        )

    return answer
