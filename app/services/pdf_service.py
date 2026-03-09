"""
e-Kres Chatbot API — PDF Analysis Tool (v2 — PyMuPDF RAG)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
PDF dosyalarini gercek olarak okur ve icerigini RAG
baglaminda kullanir. Oturum bazli PDF deposu tutar.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.core.constants import ToolName
from app.services.base_service import BaseTool

logger = logging.getLogger(__name__)

from app.services.rag_store import store_rag_context, get_session_context


def extract_text_from_pdf(file_path: str) -> tuple[str, int]:
    """
    PyMuPDF (fitz) ile PDF'den metin cikar.

    Returns:
        (metin, sayfa_sayisi) tuple'i
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(file_path)
        pages = len(doc)
        text_parts: list[str] = []

        for page_num in range(pages):
            page = doc[page_num]
            page_text = page.get_text("text").strip()
            if page_text:
                text_parts.append(f"--- Sayfa {page_num + 1} ---\n{page_text}")

        doc.close()
        full_text = "\n\n".join(text_parts)
        logger.info("PDF okundu: %s — %d sayfa, %d karakter", file_path, pages, len(full_text))
        return full_text, pages

    except ImportError:
        logger.error("PyMuPDF (fitz) kurulu degil!")
        return "", 0
    except Exception as exc:
        logger.error("PDF okuma hatasi (%s): %s", file_path, exc)
        return "", 0


class PDFAnalysisTool(BaseTool):
    """PDF bulten ve dokuman analizi araci — gercek PyMuPDF destekli."""

    @property
    def name(self) -> str:
        return ToolName.PDF_ANALYSIS.value

    @property
    def description(self) -> str:
        return (
            "PDF formatindaki bulten, duyuru ve dokumanlari analiz eder. "
            "Icerigini ozetler ve kullanicinin sorularina yanitlar uretir. "
            "Yuklenmis PDF'lerdeki bilgilere bakarak cevap verir."
        )

    async def run(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """
        PDF analizi yap.

        kwargs icinde beklenen:
            file_url (str): PDF dosya yolu.
            session_id (str): Oturum ID'si — depodaki PDF'lere bakmak icin.
        """
        session_id = kwargs.get("session_id", "")
        file_url = kwargs.get("file_url")

        # Yeni bir PDF dosyasi verilmisse oku
        if file_url and os.path.exists(file_url):
            text, pages = extract_text_from_pdf(file_url)
            if text:
                store_rag_context(session_id, "pdf", os.path.basename(file_url), text, pages)
                return {
                    "type": "pdf_analysis",
                    "status": "ok",
                    "filename": os.path.basename(file_url),
                    "pages": pages,
                    "text": text[:3000],  # LLM'e gondermek icin kisa tut
                    "message": (
                        f"PDF basariyla okundu: {os.path.basename(file_url)} "
                        f"({pages} sayfa).\n\n"
                        f"Icerik ozeti:\n{text[:1500]}"
                    ),
                }

        # Oturumda daha once yuklenenmis PDF varsa, onlara bakarak cevapla
        session_rag = get_session_context(session_id)
        session_pdfs = [item for item in session_rag if item["type"] == "pdf"]
        
        if session_pdfs:
            # Tum PDF iceriklerini birlestir (max 4000 karakter)
            combined_text = ""
            filenames = []
            for pdf_data in session_pdfs:
                filenames.append(pdf_data["source"])
                combined_text += f"\n[{pdf_data['source']}]\n{pdf_data['text']}\n"
                if len(combined_text) > 4000:
                    break

            return {
                "type": "pdf_analysis",
                "status": "ok",
                "filenames": filenames,
                "text": combined_text[:4000],
                "message": (
                    f"Yuklenmis PDF'ler ({', '.join(filenames)}) icerigi:\n\n"
                    f"{combined_text[:2000]}"
                ),
            }

        # Hicbir PDF yoksa kullaniciya bilgi ver
        return {
            "type": "pdf_analysis",
            "status": "no_pdf",
            "message": (
                "Henuz bir PDF yuklemediniz. "
                "Chat kutusunun yanindaki 📎 butonunu kullanarak "
                "bir PDF dosyasi yukleyebilirsiniz."
            ),
        }
