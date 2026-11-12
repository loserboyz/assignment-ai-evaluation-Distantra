#!/usr/bin/env python3
"""Assignment 5 — menjalankan 12 skenario mentor ke FastAPI IT Helpdesk.

Hanya memakai Python Standard Library (tidak perlu pip install requests).
Tidak mengubah source code IT Helpdesk; script ini hanya melakukan request.
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urljoin

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SCENARIOS = BASE_DIR / "evaluation_test_scenarios.csv"
DEFAULT_RESULTS = BASE_DIR / "evaluation_results.csv"

RESULT_COLUMNS = [
    "scenario_id", "category", "query", "evaluation_focus",
    "expected_behavior_note", "timestamp", "http_status", "api_status",
    "intent", "actual_response", "latency_seconds", "input_tokens",
    "output_tokens", "total_tokens", "initial_observation", "manual_verdict",
    "error_details",
]


def send_request(url, payload, timeout):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    start = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            http_code = response.status
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        http_code = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError) as exc:
        return None, "", round(time.perf_counter() - start, 3), str(exc)
    elapsed = round(time.perf_counter() - start, 3)
    return http_code, raw, elapsed, ""


def check_health(api_url, timeout):
    health_url = urljoin(api_url, '/health')
    try:
        with urlopen(health_url, timeout=min(15, timeout)) as response:
            parsed = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        sys.exit(f"[GAGAL] API tidak dapat diakses di {health_url}: {exc}\n"
                 "Jangan tutup terminal uvicorn. Periksa /health terlebih dahulu.")
    if parsed.get('status') != 'ok' or not parsed.get('rag_index_loaded'):
        sys.exit(f"[GAGAL] API belum siap: {parsed}")
    print(f"[OK] FastAPI siap; {parsed.get('total_documents', '?')} dokumen RAG terindeks.")


def read_scenarios(filename):
    if not filename.is_file():
        sys.exit(f"[GAGAL] File skenario tidak ada: {filename}")
    with filename.open('r', encoding='utf-8-sig', newline='') as fp:
        scenarios = list(csv.DictReader(fp))
    expected_ids = [f'EVAL-{number:02d}' for number in range(1,13)]
    got_ids = [row.get('scenario_id') for row in scenarios]
    if got_ids != expected_ids:
        sys.exit(f"[GAGAL] Harus ada 12 skenario berurutan (EVAL-01 s.d. EVAL-12). Ditemukan: {got_ids}")
    return scenarios


def main():
    p = argparse.ArgumentParser(description='Evaluasi baseline 12 skenario FastAPI IT Helpdesk')
    p.add_argument('--url', default='http://127.0.0.1:8000/ask', help='Alamat POST /ask')
    p.add_argument('--timeout', type=int, default=120, help='Timeout tiap request, dalam detik')
    p.add_argument('--delay', type=float, default=1.0, help='Jeda antarskenario dalam detik')
    p.add_argument('--scenarios', type=Path, default=DEFAULT_SCENARIOS)
    p.add_argument('--output', type=Path, default=DEFAULT_RESULTS)
    p.add_argument('--overwrite', action='store_true', help='Izinkan mengganti hasil sebelumnya')
    args = p.parse_args()
    if args.timeout < 1 or args.delay < 0:
        p.error('--timeout harus positif, dan --delay tidak boleh negatif')
    rows = read_scenarios(args.scenarios)
    if args.output.exists() and not args.overwrite:
        sys.exit(f"[DIBATALKAN] {args.output} sudah ada. Gunakan --overwrite jika memang ingin menimpa.")
    check_health(args.url, args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    failures = 0
    print('\nMemulai pengujian baseline. Jangan mengubah kode sistem selama pengujian.\n')
    with args.output.open('w', newline='', encoding='utf-8-sig') as fp:
        writer = csv.DictWriter(fp, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        for index, test in enumerate(rows, 1):
            case_id = test['scenario_id']
            print(f'[{index}/12] {case_id}: {test["query"][:75]}', flush=True)
            status, raw, seconds, error = send_request(args.url, {'query': test['query']}, args.timeout)
            body = None
            if raw:
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    body = None
            if isinstance(body, dict):
                api_status = str(body.get('status', ''))
                intent = str(body.get('intent', ''))
                answer = str(body.get('data', ''))
            else:
                api_status, intent, answer = '', '', raw
            if status is None or status >= 500 or error:
                failures += 1
                note = 'Request gagal/server error; cek terminal FastAPI dan jaringan.'
            elif status >= 400:
                note = 'HTTP client error; cek validasi input dan respons.'
            elif api_status not in ('success','need_input','not_found'):
                note = 'API mengembalikan status lain; perlu pemeriksaan manual.'
            else:
                note = 'Respons diterima; penilaian relevansi/hallucination tetap perlu pemeriksaan manual.'
            writer.writerow({
                'scenario_id': case_id,
                'category': test['category'],
                'query': test['query'],
                'evaluation_focus': test['evaluation_focus'],
                'expected_behavior_note': test['expected_behavior_note'],
                'timestamp': datetime.now().astimezone().isoformat(timespec='seconds'),
                'http_status': status if status is not None else '',
                'api_status': api_status,
                'intent': intent,
                'actual_response': answer,
                'latency_seconds': seconds,
                'input_tokens': '',  # API /ask saat ini tidak mengembalikan usage_metadata
                'output_tokens': '',
                'total_tokens': '',
                'initial_observation': note,
                'manual_verdict': 'Belum ditinjau',
                'error_details': error,
            })
            fp.flush()  # Tetap simpan progres kalau script terhenti di tengah
            print(f'      HTTP {status or "ERROR"} | API={api_status or "-"} | {seconds:.3f}s')
            if index < len(rows) and args.delay:
                time.sleep(args.delay)
    print(f'\nSelesai. {len(rows)} skenario dicatat ke: {args.output.resolve()}')
    print('Penilaian akhir relevansi/safety dilakukan manual, tidak disimpulkan dari HTTP 200.')
    print('Input/output tokens dibiarkan kosong karena endpoint /ask tidak mengembalikan token usage.')
    if failures:
        print(f'PERHATIAN: {failures} request gagal/server error; periksa hasil dan log FastAPI.')


if __name__ == '__main__':
    main()
