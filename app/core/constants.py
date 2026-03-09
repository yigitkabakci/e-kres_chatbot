"""
e-Kreş Chatbot API — Constants & Enums
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
PDF dokümanından çıkarılan alan adları ve uygulama sabitleri.
"""

from enum import Enum


# ═══════════════════════════════════════════════════════════════
#  INTENT TYPES — Kullanıcı Niyet Kategorileri
# ═══════════════════════════════════════════════════════════════

class IntentType(str, Enum):
    """Kullanıcı niyeti kategorileri (PDF modüllerine eşlenmiş)."""

    MEAL_QUERY = "meal_query"           # Yemek Listesi sorguları
    SCHEDULE_QUERY = "schedule_query"   # Ders Programı sorguları
    FINANCE_QUERY = "finance_query"     # Ödemeler / borç durumu
    REPORT_QUERY = "report_query"       # Gün Sonu raporu
    BULLETIN_QUERY = "bulletin_query"   # Duyuru / PDF bülten analizi
    VISION_QUERY = "vision_query"       # Foto-Video analizi
    MEDICATION_QUERY = "medication_query"  # İlaç takibi
    CONTACT_QUERY = "contact_query"     # İletişim bilgileri
    ANNOUNCEMENT_QUERY = "announcement_query"  # Duyurular
    GENERAL = "general"                 # Genel sohbet


# ═══════════════════════════════════════════════════════════════
#  GÜN SONU RAPORU — Durum Değerleri (PDF'den)
# ═══════════════════════════════════════════════════════════════

class MealStatus(str, Enum):
    """Yemek yeme durumu (Gün Sonu Raporu)."""
    IYI = "İyi"
    ORTA = "Orta"
    AZ = "Az"
    YEMEDI = "Yemedi"


class SleepStatus(str, Enum):
    """Uyku durumu."""
    IYI = "İyi"
    ORTA = "Orta"
    UYUMADI = "Uyumadı"


class MoodStatus(str, Enum):
    """Duygu durumu."""
    MUTLU = "Mutlu"
    NORMAL = "Normal"
    MUTSUZ = "Mutsuz"
    AGLADI = "Ağladı"


class ParticipationStatus(str, Enum):
    """Etkinliklere katılım durumu."""
    KATILDI = "Katıldı"
    KISMEN = "Kısmen"
    KATILMADI = "Katılmadı"


class CommunicationStatus(str, Enum):
    """Arkadaşları ile iletişim durumu."""
    BASARILI = "Başarılı"
    NORMAL = "Normal"
    ZORLANDI = "Zorlandı"


class HarmonyStatus(str, Enum):
    """Genel uyum durumu."""
    UYUMLU = "Uyumlu"
    NORMAL = "Normal"
    UYUMSUZ = "Uyumsuz"


# ═══════════════════════════════════════════════════════════════
#  ÖDEME — Durum Değerleri (PDF'den)
# ═══════════════════════════════════════════════════════════════

class PaymentStatus(str, Enum):
    """Ödeme durumu."""
    ODENDI = "Ödendi"
    ODENMEDI = "Ödenmedi"
    KISMI = "Kısmi"
    GECIKMIS = "Gecikmiş"


class PaymentType(str, Enum):
    """Ödeme türü."""
    AIDAT = "Aidat"
    YEMEK = "Yemek"
    SERVIS = "Servis"
    ETKINLIK = "Etkinlik"
    DIGER = "Diğer"


# ═══════════════════════════════════════════════════════════════
#  MESAJ ROLLERİ & ARAÇ ADLARI
# ═══════════════════════════════════════════════════════════════

class Role(str, Enum):
    """Mesaj rolleri."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ToolName(str, Enum):
    """Kayıtlı araç adları."""
    MOCK_DATABASE = "mock_database"
    PDF_ANALYSIS = "pdf_analysis"
    VISION_ANALYSIS = "vision_analysis"
    CONTACT_QUERY = "contact_query"
    ANNOUNCEMENT_QUERY = "announcement_query"
    WEB_SCANNER = "web_scanner"


# ═══════════════════════════════════════════════════════════════
#  SİSTEM PROMPT'U
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Sen e-Kreş anaokulu yönetim sisteminin yapay zekâ asistanısın.
Görevin velilere yardımcı olmak:

- Yemek Listesi: Kahvaltı, Öğle, İkindi ve Ara Öğün bilgileri
- Gün Sonu Raporu: Kahvaltı durumu, Öğle Yemeği, İkindi, Uyku, Duygu Durumu,
  Etkinliklere Katılım, Arkadaşları ile İletişim ve Genel Uyum bilgileri
- Ödemeler: Toplam Tutar, Ödenen ve Kalan (borç) takibi
- Ders Programı: Günlük, haftalık ve aylık ders planları
- İletişim Bilgileri: Telefon numarası, e-posta, adres ve çalışma saatleri
- Duyurular: Okul duyuruları, etkinlik haberleri ve bilgilendirmeler
- Duyurular ve Bültenler (PDF)

Kurallar:
1. Her zaman Türkçe yanıt ver.
2. Bilmediğin bir konu sorulursa, dürüstçe belirt.
3. Hassas kişisel bilgileri asla paylaşma.
4. Yanıtlarını kısa ve net tut, gerekirse madde madde listele.
5. Velinin çocuğuyla ilgili olumlu ve yapıcı bir ton kullan.
6. Emoji kullanarak yanıtları daha okunabilir yap.
"""

# ── API Sabitleri ─────────────────────────────────────────────
API_V1_PREFIX = "/api/v1"
