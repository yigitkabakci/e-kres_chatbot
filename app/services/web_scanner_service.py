"""
e-Kres Chatbot API — Web Scanner Tool
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Kullanicidan alinan web linklerinin icerigini asenkron olarak
tarar ve oturum bazli RAG deposuna kaydeder.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.services.base_service import BaseTool

logger = logging.getLogger(__name__)


def extract_text_from_url(url: str) -> tuple[str, int]:
    """
    Belirtilen URL'deki sayfanin ana metnini BeautifulSoup ile cikarir.
    Returns (metin, kelime_sayisi).
    """
    try:
        response = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Gereksiz etiketleri temizle
        for script in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            script.extract()

        text = soup.get_text(separator="\n", strip=True)
        # Bos satirlari temizle
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned_text = "\n".join(lines)
        
        word_count = len(cleaned_text.split())
        logger.info("URL okundu: %s — %d kelime, %d karakter", url, word_count, len(cleaned_text))
        
        return cleaned_text, word_count

    except requests.RequestException as e:
        logger.error("URL erisim hatasi (%s): %s", url, e)
        return "", 0
    except Exception as exc:
        logger.error("URL okuma hatasi (%s): %s", url, exc)
        return "", 0


class WebScannerTool(BaseTool):
    """Web iceriklerini analiz etme araci."""

    @property
    def name(self) -> str:
        return "web_scanner"

    @property
    def description(self) -> str:
        return (
            "Web sayfalarinin icerigini analiz eder. "
            "Kullaniciya taranmis web sayfalarina bagli yanitlar uretir."
        )

    async def run(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """
        Web tarama analiz araci.
        Genellikle dogrudan sorgu icin kullanilir.
        """
        from app.services.rag_store import get_session_context

        session_id = kwargs.get("session_id", "")
        
        # Sadece Web belgelerini al
        session_rag = get_session_context(session_id)
        session_webs = [item for item in session_rag if item["type"] == "web"]
        
        if session_webs:
            combined_text = ""
            urls = []
            for web_data in session_webs:
                urls.append(web_data["source"])
                combined_text += f"\n[{web_data['source']}]\n{web_data['text']}\n"
                if len(combined_text) > 4000:
                    break

            return {
                "type": "web_analysis",
                "status": "ok",
                "urls": urls,
                "text": combined_text[:4000],
                "message": (
                    f"Taranmis web sayfalari ({', '.join(urls)}) icerigi:\n\n"
                    f"{combined_text[:2000]}"
                ),
            }

        return {
            "type": "web_analysis",
            "status": "no_web",
            "message": "Henuz analiz edilmis bir web sayfasi bulunmuyor."
        }
