
"""
Router IT Helpdesk Assistant
Assignment 5 - Optimasi EVAL-09

Mendukung:
1. FAQ berbasis RAG
2. Pengecekan status tiket
3. Pertanyaan gabungan FAQ + tiket
"""

import re

from app.rag import answer_from_knowledge_base
from app.tools import get_ticket_status


TICKET_ID_PATTERN = re.compile(
    r"\bTICKET-\d{4}\b",
    re.IGNORECASE
)

TICKET_STATUS_KEYWORDS = [
    "status tiket",
    "status ticket",
    "cek tiket",
    "cek ticket",
    "cek status",
    "lacak tiket",
    "tracking tiket",
    "ticket status",
    "tiket saya",
    "ticket saya",
    "nomor tiket",
    "nomor ticket",
    "perkembangan tiket",
    "progress tiket"
]


async def detect_intent(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        return "unknown"

    normalized_query = query.lower().strip()

    if TICKET_ID_PATTERN.search(query):
        return "ticket_status"

    for keyword in TICKET_STATUS_KEYWORDS:
        if keyword in normalized_query:
            return "ticket_status"
    if normalized_query in {
        "halo",
        "hai",
        "haii",
        "hello",
        "hi",
        "selamat pagi",
        "selamat siang",
        "selamat sore",
        "selamat malam",
    }:
        return "greeting"

    return "faq"


def extract_ticket_id(query: str) -> str:
    if not isinstance(query, str):
        return ""

    match = TICKET_ID_PATTERN.search(query)

    if match:
        return match.group(0).upper()

    return ""


def extract_mixed_faq_query(query: str) -> str:
    """
    Memisahkan pertanyaan gabungan FAQ dan tiket.
    """

    parts = [
        part.strip()
        for part in re.split(
            r"\s+(?:dan|serta|sekalian)\s+",
            query,
            flags=re.IGNORECASE
        )
        if part.strip()
    ]

    if len(parts) < 2:
        return ""

    ticket_parts = [
        part for part in parts
        if TICKET_ID_PATTERN.search(part)
        or any(
            keyword in part.lower()
            for keyword in TICKET_STATUS_KEYWORDS
        )
    ]

    faq_parts = [
        part for part in parts
        if part not in ticket_parts
    ]

    if not ticket_parts or not faq_parts:
        return ""

    return " dan ".join(faq_parts)


async def handle_query(query: str) -> dict:
    """
    Fungsi utama Intelligent Router.
    """

    # 1. Validasi input
    if not isinstance(query, str) or not query.strip():
        return {
            "status": "error",
            "intent": "unknown",
            "data": "Pertanyaan tidak boleh kosong."
        }

    # 2. Optimasi EVAL-09: Multi-intent
    faq_query = extract_mixed_faq_query(query)

    if faq_query:
        faq_answer = await answer_from_knowledge_base(
            faq_query
        )

        ticket_id = extract_ticket_id(query)

        if ticket_id:
            ticket_answer = get_ticket_status(ticket_id)

            result_status = (
                "not_found"
                if "tidak ditemukan" in ticket_answer.lower()
                else "success"
            )
        else:
            ticket_answer = (
                "Mohon sertakan ID tiket Anda dengan "
                "format TICKET-0001 agar saya dapat "
                "memeriksa statusnya."
            )

            result_status = "need_input"

        return {
            "status": result_status,
            "intent": "multi_intent",
            "data": (
                f"Informasi helpdesk:\n{faq_answer}\n\n"
                f"Informasi status tiket:\n{ticket_answer}"
            )
        }

    # 3. Deteksi intent biasa
    intent = await detect_intent(query)

    # 4. Jalur pengecekan tiket
    if intent == "ticket_status":
        ticket_id = extract_ticket_id(query)

        if not ticket_id:
            return {
                "status": "need_input",
                "intent": "ticket_status",
                "data": (
                    "Mohon sertakan ID tiket Anda "
                    "dengan format TICKET-0001 "
                    "agar saya dapat memeriksa statusnya."
                )
            }

        data = get_ticket_status(ticket_id)

        result_status = (
            "not_found"
            if "tidak ditemukan" in data.lower()
            else "success"
        )

        return {
            "status": result_status,
            "intent": "ticket_status",
            "data": data
        }

   # 5. Jalur sapaan tanpa RAG
    elif intent == "greeting":
        return {
            "status": "success",
            "intent": "greeting",
            "data": "Halo! Ada yang bisa saya bantu terkait layanan IT Helpdesk?"
        }
    
    
   # 5. Jalur FAQ RAG

    elif intent == "faq":
        data = await answer_from_knowledge_base(query)

        return {
            "status": "success",
            "intent": "faq",
            "data": data
        }

    # 6. Intent tidak dikenali
    return {
        "status": "error",
        "intent": "unknown",
        "data": "Maaf, saya belum memahami permintaan Anda."
    }
