"""
e-Kres Chatbot API — File Service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Excel ve JSON dosyalarini okumak icin servis.
Ogretmenler ogrenci listesi, etkinlik takvimi gibi
dosyalari yukleyebilir.

Gereksinim: pandas, openpyxl (requirements.txt'e eklenmeli)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.services.base_service import BaseTool

logger = logging.getLogger(__name__)

# Yuklenecek dosyalar icin dizin
DATA_DIR = Path(__file__).parent.parent.parent / "data"


class FileService:
    """
    Excel ve JSON dosya okuyucu.

    Kullanim:
        fs = FileService()
        data = fs.read_excel("ogrenci_listesi.xlsx")
        data = fs.read_json("etkinlik_takvimi.json")
    """

    def __init__(self) -> None:
        # data/ dizinini olustur (yoksa)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("FileService hazir, data dizini: %s", DATA_DIR)

    def read_excel(
        self,
        filename: str,
        sheet_name: str | int = 0,
    ) -> list[dict[str, Any]]:
        """
        Excel dosyasini oku ve dict listesi olarak dondur.

        Args:
            filename: data/ altindaki dosya adi (orn: 'ogrenci_listesi.xlsx')
            sheet_name: Okunacak sayfa adi veya indeksi.

        Returns:
            list[dict]: Her satir bir dict.
        """
        filepath = DATA_DIR / filename
        if not filepath.exists():
            logger.warning("Excel dosyasi bulunamadi: %s", filepath)
            return []

        try:
            import pandas as pd

            df = pd.read_excel(filepath, sheet_name=sheet_name)
            records = df.to_dict(orient="records")
            logger.info("Excel okundu: %s (%d satir)", filename, len(records))
            return records
        except ImportError:
            logger.error("pandas/openpyxl yuklu degil — pip install pandas openpyxl")
            return []
        except Exception as exc:
            logger.error("Excel okuma hatasi (%s): %s", filename, exc)
            return []

    def read_json(self, filename: str) -> Any:
        """
        JSON dosyasini oku.

        Args:
            filename: data/ altindaki dosya adi (orn: 'etkinlik_takvimi.json')

        Returns:
            Parsed JSON verisi.
        """
        filepath = DATA_DIR / filename
        if not filepath.exists():
            logger.warning("JSON dosyasi bulunamadi: %s", filepath)
            return {}

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("JSON okundu: %s", filename)
            return data
        except Exception as exc:
            logger.error("JSON okuma hatasi (%s): %s", filename, exc)
            return {}

    def list_files(self) -> list[str]:
        """data/ dizinindeki dosyalari listele."""
        if not DATA_DIR.exists():
            return []
        return [f.name for f in DATA_DIR.iterdir() if f.is_file()]

    def save_json(self, filename: str, data: Any) -> bool:
        """JSON dosyasi kaydet."""
        filepath = DATA_DIR / filename
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("JSON kaydedildi: %s", filename)
            return True
        except Exception as exc:
            logger.error("JSON kaydetme hatasi (%s): %s", filename, exc)
            return False


class FileQueryTool(BaseTool):
    """Dosya sorgulama araci — Excel/JSON verilerini chatbot'a acar."""

    @property
    def name(self) -> str:
        return "file_query"

    @property
    def description(self) -> str:
        return (
            "data/ klasorundeki Excel ve JSON dosyalarini okur. "
            "Ogrenci listesi, etkinlik takvimi gibi verilere erisir."
        )

    def __init__(self) -> None:
        self._fs = FileService()

    async def run(self, query: str, **kwargs: Any) -> dict[str, Any]:
        files = self._fs.list_files()
        if not files:
            return {
                "type": "file_query",
                "message": (
                    "data/ klasorunde henuz dosya yok. "
                    "Ogretmen Excel veya JSON dosyasi yukleyebilir."
                ),
            }

        results: list[str] = [f"Mevcut dosyalar: {', '.join(files)}"]
        for f in files:
            if f.endswith((".xlsx", ".xls")):
                rows = self._fs.read_excel(f)
                results.append(f"{f}: {len(rows)} satir")
            elif f.endswith(".json"):
                data = self._fs.read_json(f)
                results.append(f"{f}: {type(data).__name__}")

        return {
            "type": "file_query",
            "data": {"files": files},
            "message": "\n".join(results),
        }
