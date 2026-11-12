
"""
Modul Tools:
Mengambil informasi status tiket dari mock_tickets.csv.
"""

from pathlib import Path
from functools import lru_cache
import pandas as pd


# Menentukan lokasi CSV berdasarkan lokasi file ini
MOCK_TICKETS_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "mock_tickets.csv"
)


@lru_cache(maxsize=1)
def load_tickets():
    """
    Membaca data tiket dan menyimpannya dalam cache.
    """

    if not MOCK_TICKETS_PATH.exists():
        raise FileNotFoundError(
            f"File tiket tidak ditemukan: {MOCK_TICKETS_PATH}"
        )

    df = pd.read_csv(MOCK_TICKETS_PATH)

    required_columns = {
        "ticket_id",
        "employee_name",
        "category",
        "subject",
        "status",
        "last_update"
    }

    if not required_columns.issubset(df.columns):
        raise ValueError(
            "Struktur kolom mock_tickets.csv tidak sesuai."
        )

    return df.fillna("")


def get_ticket_status(ticket_id: str) -> str:
    """
    Mencari status tiket berdasarkan ticket_id.
    """

    # 1. Validasi ticket ID
    if not isinstance(ticket_id, str) or not ticket_id.strip():
        return "Ticket ID tidak valid atau kosong."

    # 2. Normalisasi ticket ID
    ticket_id = ticket_id.strip().upper()

    # 3. Membaca data tiket
    df = load_tickets()

    # 4. Mencari tiket berdasarkan ID
    result = df[
        df["ticket_id"].astype(str).str.strip().str.upper()
        == ticket_id
    ]

    # 5. Jika tiket tidak ditemukan
    if result.empty:
        return (
            f"Tiket {ticket_id} tidak ditemukan "
            "dalam database."
        )

    # 6. Mengambil data tiket
    ticket = result.iloc[0]

    # 7. Menyusun jawaban
    return (
        f"Informasi Tiket: {ticket['ticket_id']}\n"
        f"Nama Karyawan: {ticket['employee_name']}\n"
        f"Kategori: {ticket['category']}\n"
        f"Subjek: {ticket['subject']}\n"
        f"Status: {ticket['status']}\n"
        f"Update Terakhir: {ticket['last_update']}"
    )
