# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000/api/v1"
CHAT_URL = f"{BASE_URL}/chat"
AUTH_URL = f"{BASE_URL}/chat/parent-auth"
CLIENT_CONFIG_URL = f"{BASE_URL}/chat/client-config"
UPLOAD_PDF_URL = f"{BASE_URL}/chat/upload-pdf"
ADMIN_STATS_URL = f"{BASE_URL}/admin/stats"
ADMIN_KEY = "admin-panel-key"
PARENT_PHONE = "05051234567"
SESSION_ID = "eval-suite-20260309"
RAG_SESSION_ID = "eval-rag-20260309"

os.environ["PYTHONIOENCODING"] = "utf-8"


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def fetch_client_config() -> dict:
    request = urllib.request.Request(CLIENT_CONFIG_URL, method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


CLIENT_CONFIG = fetch_client_config()
API_KEY = CLIENT_CONFIG.get("api_key", "")


def build_headers(extra: dict | None = None) -> dict:
    headers = {"Accept": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    if extra:
        headers.update(extra)
    return headers


def request_json(url: str, method: str = "GET", body: dict | None = None, headers: dict | None = None, expected_status: int | None = 200) -> tuple[int, dict]:
    data = None
    request_headers = build_headers(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            payload = response.read().decode("utf-8")
            parsed = json.loads(payload) if payload else {}
            if expected_status is not None and response.status != expected_status:
                raise AssertionError(f"Beklenen HTTP {expected_status}, alinan {response.status}")
            return response.status, parsed
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="ignore")
        parsed = json.loads(payload) if payload else {}
        if expected_status is not None and exc.code != expected_status:
            raise AssertionError(f"Beklenen HTTP {expected_status}, alinan {exc.code} | {parsed}") from exc
        return exc.code, parsed


def make_simple_pdf(path: Path) -> None:
    lines = [
        "Mart Bulteni",
        "Aile bulusmasi 18 Mart 2026 saat 14:00.",
        "Mavi grup gezi saati 10:30.",
        "Gerekli belge: mavi sapka.",
    ]
    text_commands = ["BT", "/F1 14 Tf", "50 760 Td"]
    for index, line in enumerate(lines):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if index == 0:
            text_commands.append(f"({escaped}) Tj")
        else:
            text_commands.append("0 -24 Td")
            text_commands.append(f"({escaped}) Tj")
    text_commands.append("ET")
    stream = "\n".join(text_commands).encode("latin-1", errors="ignore")

    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Count 1 /Kids [3 0 R] >>endobj\n",
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n",
        b"4 0 obj<< /Length " + str(len(stream)).encode("ascii") + b" >>stream\n" + stream + b"\nendstream\nendobj\n",
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
    ]

    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(content))
        content.extend(obj)
    xref_start = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(f"trailer<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("ascii"))
    path.write_bytes(content)


RAG_UPLOADED = False
RAG_FILENAME = "mart-bulten-eval.pdf"


def ensure_rag_pdf_uploaded() -> None:
    global RAG_UPLOADED
    if RAG_UPLOADED:
        return

    temp_dir = Path(tempfile.gettempdir())
    pdf_path = temp_dir / RAG_FILENAME
    make_simple_pdf(pdf_path)
    boundary = f"----CodexBoundary{uuid.uuid4().hex}"
    file_bytes = pdf_path.read_bytes()
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b'Content-Disposition: form-data; name="session_id"\r\n\r\n')
    body.extend(RAG_SESSION_ID.encode("utf-8"))
    body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{RAG_FILENAME}"\r\n'.encode("utf-8"))
    body.extend(b"Content-Type: application/pdf\r\n\r\n")
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    headers = build_headers({"Content-Type": f"multipart/form-data; boundary={boundary}"})
    request = urllib.request.Request(UPLOAD_PDF_URL, data=bytes(body), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if response.status != 200 or payload.get("status") != "ok":
                raise AssertionError(f"PDF yukleme basarisiz: {payload}")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="ignore")
        raise AssertionError(f"PDF yukleme HTTP {exc.code}: {payload}") from exc

    RAG_UPLOADED = True


passed = 0
total = 0
results: list[dict] = []


def run_test(category: str, name: str, fn) -> None:
    global passed, total
    total += 1
    try:
        detail = fn() or "Beklenen yanit alindi."
        passed += 1
        results.append({"category": category, "name": name, "status": "Basarili", "detail": detail})
        safe_print(f"[OK] {category} | {name} -> {detail}")
    except Exception as exc:
        message = str(exc)
        results.append({"category": category, "name": name, "status": "Basarisiz", "detail": message})
        safe_print(f"[FAIL] {category} | {name} -> {message}")


def send_chat(message: str, *, session_id: str = SESSION_ID, parent_phone: str | None = PARENT_PHONE, expected_status: int = 200) -> tuple[int, dict]:
    return request_json(
        CHAT_URL,
        method="POST",
        body={
            "session_id": session_id,
            "message": message,
            "parent_phone": parent_phone,
            "password": None,
        },
        expected_status=expected_status,
    )


def finance_total() -> str:
    _, payload = send_chat("Borcum ne kadar?")
    assert "30,380,000" in payload["response"], payload["response"]
    assert payload.get("source") == "mock_database.json", payload
    return "Toplam borc 30.380.000 TL dogrulandi"


def finance_paid() -> str:
    _, payload = send_chat("Ne kadar odeme yaptim?")
    assert "380,000" in payload["response"], payload["response"]
    assert payload.get("page") == 9, payload
    return "Odenen tutar 380.000 TL dogrulandi"


def finance_remaining() -> str:
    _, payload = send_chat("Kalan bakiyem nedir?")
    assert "30,000,000" in payload["response"], payload["response"]
    return "Kalan bakiye 30.000.000 TL dogrulandi"


def education_meal() -> str:
    _, payload = send_chat("Bugun ne yemek var?", parent_phone=None)
    assert "Alaca corbasi" in payload["response"], payload["response"]
    assert payload.get("source") == "mock_database.json", payload
    assert payload.get("page") == 5, payload
    return "Alaca corbasi ve kaynak etiketi geldi"


def education_schedule() -> str:
    _, payload = send_chat("Bugunku ders programi ne?", parent_phone=None)
    assert "Turkce Dil Etkinligi" in payload["response"], payload["response"]
    return "Turkce Dil Etkinligi bulundu"


def education_report() -> str:
    _, payload = send_chat("Cocugum nasil?")
    assert "Uyku: Iyi" in payload["response"], payload["response"]
    assert "Genel Uyum: Uyumlu" in payload["response"], payload["response"]
    assert payload.get("page") == 8, payload
    return "Uyku ve genel uyum bilgisi geldi"


def rag_family_meeting() -> str:
    ensure_rag_pdf_uploaded()
    _, payload = send_chat("Yukledigim PDF'te aile bulusmasi tarihi nedir? PDF bilgisine bak.", session_id=RAG_SESSION_ID, parent_phone=None)
    assert "18 Mart 2026" in payload["response"], payload["response"]
    return "18 Mart 2026 bulundu"


def rag_trip_time() -> str:
    ensure_rag_pdf_uploaded()
    _, payload = send_chat("PDF'te gezi saati nedir?", session_id=RAG_SESSION_ID, parent_phone=None)
    assert "10:30" in payload["response"], payload["response"]
    return "10:30 bulundu"


def rag_required_item() -> str:
    ensure_rag_pdf_uploaded()
    _, payload = send_chat("PDF'te hangi belge isteniyor?", session_id=RAG_SESSION_ID, parent_phone=None)
    assert "mavi sapka" in payload["response"].lower(), payload["response"]
    return "mavi sapka bulundu"


def security_unauthorized_parent() -> str:
    _, payload = send_chat("Borcum ne kadar?", parent_phone=None)
    assert "Lutfen once telefon numaranizi girin." in payload["response"], payload["response"]
    return "Yetkisiz borc sorgusu reddedildi"


def security_wrong_admin_key() -> str:
    status_code, payload = request_json(ADMIN_STATS_URL, headers={"X-Admin-Key": "yanlis-admin-key"}, expected_status=401)
    assert status_code == 401, payload
    assert "Gecersiz admin API anahtari" in payload.get("detail", ""), payload
    return "HTTP 401 ve gecersiz anahtar mesaji alindi"


def security_sql_injection() -> str:
    status_code, payload = request_json(AUTH_URL, method="POST", body={"phone": "' OR 1=1 --"}, expected_status=404)
    assert status_code == 404, payload
    assert "Bu numara ile kayitli veli bulunamadi." in payload.get("detail", ""), payload
    return "Kayitli veli bulunamadi mesaji alindi"


def system_empty_message() -> str:
    status_code, payload = request_json(
        CHAT_URL,
        method="POST",
        body={"session_id": SESSION_ID, "message": "", "parent_phone": PARENT_PHONE, "password": None},
        expected_status=422,
    )
    assert status_code == 422, payload
    return "Bos mesaj dogrulamasi aktif"


def system_too_long_message() -> str:
    status_code, payload = request_json(
        CHAT_URL,
        method="POST",
        body={"session_id": SESSION_ID, "message": "x" * 5000, "parent_phone": PARENT_PHONE, "password": None},
        expected_status=422,
    )
    assert status_code == 422, payload
    return "Uzun mesaj limiti calisiyor"


def system_fallback_check() -> str:
    before_status, before = request_json(ADMIN_STATS_URL, headers={"X-Admin-Key": ADMIN_KEY}, expected_status=200)
    before_total = sum((before.get("ai") or {}).get("fallbacks", {}).values())
    assert before_status == 200, before

    send_chat("Bu tamamen genel bir deneme sorusudur.", session_id="eval-fallback-20260309", parent_phone=None)

    after_status, after = request_json(ADMIN_STATS_URL, headers={"X-Admin-Key": ADMIN_KEY}, expected_status=200)
    after_total = sum((after.get("ai") or {}).get("fallbacks", {}).values())
    assert after_status == 200, after
    assert after_total > before_total, f"Fallback sayaci artmadi | once={before_total} sonra={after_total}"
    return f"Fallback sayaclari artti ({before_total} -> {after_total})"


TESTS = [
    ("Finans", "Toplam borc dogrulugu", finance_total),
    ("Finans", "Odenen tutar dogrulugu", finance_paid),
    ("Finans", "Kalan bakiye dogrulugu", finance_remaining),
    ("Egitim", "Yemek listesi Alaca corbasi", education_meal),
    ("Egitim", "Ders programi dogrulugu", education_schedule),
    ("Egitim", "Gun sonu raporu dogrulugu", education_report),
    ("RAG", "PDF iceriginde aile bulusmasi tarihi", rag_family_meeting),
    ("RAG", "PDF iceriginde gezi saati", rag_trip_time),
    ("RAG", "PDF iceriginde istenen belge", rag_required_item),
    ("Guvenlik", "Yetkisiz veli borc erisimi engelleniyor", security_unauthorized_parent),
    ("Guvenlik", "Yanlis API key ile admin stats reddediliyor", security_wrong_admin_key),
    ("Guvenlik", "SQL injection giris denemesi reddediliyor", security_sql_injection),
    ("Sistem", "Bos mesaj 422 donuyor", system_empty_message),
    ("Sistem", "Cok uzun mesaj 422 donuyor", system_too_long_message),
    ("Sistem", "Gemini fallback sayaclari izleniyor", system_fallback_check),
]

for category, name, fn in TESTS:
    run_test(category, name, fn)

score = round((passed / total) * 100) if total else 0
safe_print("\nDetayli Sonuclar:")
for item in results:
    safe_print(f"- [{item['status']}] {item['category']} | {item['name']} | {item['detail']}")

safe_print(f"\nGenel Basari Puani: %{score}")
sys.exit(0 if passed == total else 1)
