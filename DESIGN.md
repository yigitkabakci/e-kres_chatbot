# e-Kreş Chatbot API — Mimari Tasarım Dokümanı

## 🎯 Vizyon

e-Kreş Chatbot API ("Brain"), anaokulu velilerine yapay zekâ destekli bilgi hizmeti sunan bir **Domain-Driven Design** tabanlı REST API'sidir. Veliler doğal dil ile soru sorabilir; sistem otomatik olarak niyeti sınıflandırır, uygun veri kaynağına yönlendirir ve LLM ile doğal dil yanıtı üretir.

---

## 🏗️ Mimari Genel Bakış

```
┌──────────────────────────────────────────────────────┐
│                    İstemci (Veli)                     │
│              (Web Widget / Mobil / API)               │
└──────────────────────┬───────────────────────────────┘
                       │ HTTP/JSON
                       ▼
┌──────────────────────────────────────────────────────┐
│                 FRONTEND KATMANI                      │
│  ┌──────────────────────────────────────────────┐    │
│  │  static/index.html + style.css + script.js   │    │
│  │  Bordo/altın branded chat widget (sağ alt)   │    │
│  │  6 hızlı erişim butonu → /api/v1/chat POST   │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              MIDDLEWARE KATMANI                       │
│  ┌──────────┐ ┌──────────────┐ ┌──────────────────┐  │
│  │   CORS   │ │   Logging    │ │  Error Handler   │  │
│  └──────────┘ └──────────────┘ └──────────────────┘  │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              API KATMANI  (app/api/v1/)               │
│  ┌──────────────────────────────────────────────┐    │
│  │  chat_router.py                               │    │
│  │  POST /chat  │  GET /history  │  GET /health  │    │
│  └──────────────────────────────────────────────┘    │
│            │ Depends() — DI                          │
└────────────┼─────────────────────────────────────────┘
             ▼
┌──────────────────────────────────────────────────────┐
│           SERVİS KATMANI  (app/services/)            │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │             ChatService (Orkestratör)           │  │
│  │  ┌───────────────┐  ┌─────────────────────┐   │  │
│  │  │  AIService     │  │  InMemoryStorage    │   │  │
│  │  │  (Gemini LLM)  │  │  (BaseMemory ABC)   │   │  │
│  │  └───────────────┘  └─────────────────────┘   │  │
│  │                                                │  │
│  │  10 Kayıtlı Araç (Tool Registry):             │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────┐ │  │
│  │  │ MealQuery   │ │ ReportQuery │ │ Payment │ │  │
│  │  │ Schedule    │ │ Contact     │ │ Announce│ │  │
│  │  │ FileQuery   │ │ PDFAnalysis │ │ Vision  │ │  │
│  │  │ WebScanner  │ │             │ │         │ │  │
│  │  └─────────────┘ └─────────────┘ └─────────┘ │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

---

## 🤖 LLM Entegrasyonu — Google Gemini Flash

Proje, **Google Gemini 2.5 Flash** modelini kullanır. Bu model, düşük gecikme süresi ve yüksek performansıyla gerçek zamanlı chatbot uygulamaları için idealdir.

| Parametre | Değer |
|---|---|
| Model | `gemini-2.5-flash` |
| Temperature | `0.7` |
| Max Tokens | `2048` |
| SDK | `google-generativeai` |

### Fail-Safe Mekanizması (RAG)
Gemini API kota aşımında (429 / ResourceExhausted) sistem otomatik olarak:
1. **Intent sınıflandırmada:** Keyword-based fallback devreye girer
2. **Yanıt üretimde:** Tool'un ürettiği hazır Türkçe metin direkt döner
3. Kullanıcı hiçbir kesinti yaşamaz

---

## 📐 Tasarım Prensipleri

### 1. Domain-Driven Design (DDD)
Her katmanın tek sorumluluğu vardır:

| Katman | Sorumluluk | Klasör |
|---|---|---|
| **Core** | Konfigürasyon, sabitler, güvenlik | `app/core/` |
| **Schemas** | Veri doğrulama (Request/Response) | `app/schemas/` |
| **Services** | İş mantığı, AI, araçlar | `app/services/` |
| **Middlewares** | Cross-cutting concerns | `app/middlewares/` |
| **API** | HTTP endpoint tanımları | `app/api/v1/` |
| **Frontend** | Static chat widget UI | `static/` |

### 2. Tool Pattern (Araç Deseni)
`BaseTool(ABC)` soyut sınıfından türetilen her araç, `execute(input_data)` metodu ile çalışır:

```python
class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    async def execute(self, input_data: dict) -> dict: ...
```

**10 Kayıtlı Araç:**

| # | Araç | Açıklama | Veri Kaynağı |
|---|---|---|---|
| 1 | `MealQueryTool` | Günlük yemek menüsü | KnowledgeService (PDF S.5) |
| 2 | `ReportQueryTool` | Gün sonu raporu | KnowledgeService (PDF S.8) |
| 3 | `PaymentQueryTool` | Ödeme/borç takibi | KnowledgeService (PDF S.9) |
| 4 | `ScheduleQueryTool` | Ders programı | KnowledgeService (PDF S.4) |
| 5 | `ContactQueryTool` | İletişim bilgileri | Sabit veri (fallback) |
| 6 | `AnnouncementQueryTool` | Duyurular | Sabit veri (fallback) |
| 7 | `FileQueryTool` | Excel/JSON dosya okuma | FileService |
| 8 | `PDFAnalysisTool` | PDF bülten analizi | Unified RAG Store |
| 9 | `VisionAnalysisTool` | Görsel analiz | Stub (genişletilebilir) |
| 10| `WebScannerTool`  | Web sitesi tarama | Unified RAG Store & BeautifulSoup |

### 3. Pydantic v2 Schema Modelleri
Tüm Request/Response modelleri `pydantic.BaseModel`'den türetilir:

```python
class ChatRequest(BaseModel):
    session_id: str       # UUID formatında oturum kimliği
    message: str          # Kullanıcı mesajı (max 4096 karakter)
    attachments: list[Attachment] | None  # Opsiyonel dosya ekleri
```

**Domain Modelleri:** `DailyMenu`, `DailyReport`, `PaymentSummary`, `PaymentItem`, `DailySchedule`, `ScheduleItem` — PDF dokümanındaki alanlarla birebir uyumlu.

### 4. BaseMemory Pattern
```python
class BaseMemory(ABC):
    async def add_message(...): ...
    async def get_history(...): ...
    async def clear(...): ...
```

**Şu an:** `InMemoryStorage` (dict tabanlı)
**İleride:** `RedisMemory` implementasyonu → sadece ABC'yi implement et, `ChatService`'e enjekte et.

### 5. Dependency Injection
```python
@router.post("/chat")
async def send_message(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
):
```

Servis katmanı router'dan tamamen bağımsızdır. Test'te mock servisler kolayca enjekte edilebilir.

---

## 🎨 Frontend — Chat Widget

Sağ alt köşede açılıp kapanan modern sohbet widget'ı:

| Özellik | Detay |
|---|---|
| Marka Renkleri | Bordo `#470101` + Altın `#d9b102` |
| Font | Inter (Google Fonts) |
| tema | Dark glassmorphism |
| Animasyonlar | Scale+fade open/close, typing dots, message slide-in |
| Hızlı Butonlar | Yemek, Ödeme, Rapor, Program, Duyuru, İletişim |
| Responsive | Mobilde tam ekran widget |

### İstek Akışı (Frontend → Backend)
```
Kullanıcı butona basar veya mesaj yazar
  → script.js: fetch("/api/v1/chat", { session_id, message })
    → FastAPI Router → ChatService.process_message()
      → 1. Mesajı hafızaya kaydet
      → 2. AIService.classify_intent() — Niyet sınıflandırma
      → 3. Intent → Tool eşleme → Tool.execute()
      → 4. AIService.generate() — Tool sonucu + geçmiş ile LLM yanıtı
      → 5. Yanıtı hafızaya kaydet
    ← ChatResponse { response, intent, tool_used, metadata }
  ← script.js: appendMessage() ile DOM'a ekle
```

---

## 🚀 Genişletilebilirlik Yol Haritası

| Özellik | Durum | Strateji |
|---|---|---|
| KnowledgeService (RAG) | ✅ Aktif | Yemek, rapor, ödeme, program verileri |
| İletişim Bilgileri | ✅ Aktif | `ContactQueryTool` — sabit veri |
| Duyurular | ✅ Aktif | `AnnouncementQueryTool` — sabit veri |
| Chat Widget UI | ✅ Aktif | static/ klasöründe HTML/CSS/JS |
| PDF Bülten Analizi | 🔲 Stub | `PDFAnalysisTool` → PyMuPDF + RAG |
| Görsel Analiz | 🔲 Stub | `VisionAnalysisTool` → Gemini Vision |
| Redis Memory | 🔲 Planlı | `RedisMemory(BaseMemory)` implementasyonu |
| LangChain Agent | 🔲 Planlı | `AgentExecutor` ile tool orchestration |
| Gerçek Veritabanı | 🔲 Planlı | `DatabaseTool(BaseTool)` → SQLAlchemy |

---

## 📦 Klasör Yapısı

```
chatbot/
├── main.py                          # Entry point + StaticFiles mount
├── requirements.txt
├── .env / .env.example
├── DESIGN.md                        # Bu dosya
├── test_api.py                      # Fail-safe test suite
│
├── static/                          # Frontend chat widget
│   ├── index.html                   # Landing page + widget markup
│   ├── style.css                    # Bordo/altın design system
│   └── script.js                    # Widget logic + API integration
│
├── app/
│   ├── api/v1/
│   │   └── chat_router.py           # Endpoint'ler + DI
│   ├── core/
│   │   ├── config.py                # Pydantic Settings
│   │   ├── constants.py             # Enum + sabitler (9 intent)
│   │   └── security.py              # API key doğrulama
│   ├── schemas/
│   │   └── chat.py                  # Pydantic v2 Request/Response
│   ├── services/
│   │   ├── base_service.py          # BaseTool + BaseMemory ABC
│   │   ├── chat_service.py          # Orkestratör (fail-safe v3)
│   │   ├── ai_service.py            # Gemini 2.5 Flash LLM
│   │   ├── knowledge_service.py     # RAG bilgi tabanı
│   │   ├── langchain_tools.py       # 9 araç (tool) kaydı
│   │   ├── mock_database.py         # Mock veriler
│   │   ├── file_service.py          # Excel/JSON okuma
│   │   ├── pdf_service.py           # PDF Tool (stub)
│   │   └── vision_service.py        # Vision Tool (stub)
│   └── middlewares/
│       ├── cors.py
│       ├── logging_middleware.py
│       └── error_handler.py
```

---

## ▶️ Hızlı Başlangıç

```bash
# 1. Bağımlılıkları kur
pip install -r requirements.txt

# 2. .env dosyasını oluştur
copy .env.example .env
# GOOGLE_API_KEY değerini düzenle

# 3. Sunucuyu başlat
uvicorn main:app --reload --port 8000

# 4. Arayüz
# http://localhost:8000        → Chat widget
# http://localhost:8000/docs   → Swagger UI
# http://localhost:8000/redoc  → ReDoc
```

## Kalite Guvence ve Test Sonuclari

15 soruluk eval seti `py -3.11 test_api.py` komutu ile 9 Mart 2026 tarihinde canli servis uzerinde calistirildi.

| Kategori | Senaryo | Durum | Not |
|---|---|---|---|
| Finans | Toplam borc dogrulugu | Basarili | 30.380.000 TL dogrulandi |
| Finans | Odenen tutar dogrulugu | Basarili | 380.000 TL dogrulandi |
| Finans | Kalan bakiye dogrulugu | Basarili | 30.000.000 TL dogrulandi |
| Egitim | Yemek listesi Alaca corbasi | Basarili | `mock_database.json` / Sayfa 5 etiketi ile dondu |
| Egitim | Ders programi dogrulugu | Basarili | Turkce Dil Etkinligi bulundu |
| Egitim | Gun sonu raporu dogrulugu | Basarili | Uyku ve genel uyum verisi dogrulandi |
| RAG | PDF iceriginde aile bulusmasi tarihi | Basarili | 18 Mart 2026 bulundu |
| RAG | PDF iceriginde gezi saati | Basarili | 10:30 bulundu |
| RAG | PDF iceriginde istenen belge | Basarili | mavi sapka bulundu |
| Guvenlik | Yetkisiz veli borc erisimi engelleniyor | Basarili | Telefon numarasi olmadan veri verilmedi |
| Guvenlik | Yanlis API key ile admin stats reddediliyor | Basarili | HTTP 401 |
| Guvenlik | SQL injection giris denemesi reddediliyor | Basarili | Kayitli veli bulunamadi mesaji dondu |
| Sistem | Bos mesaj 422 donuyor | Basarili | Schema validation aktif |
| Sistem | Cok uzun mesaj 422 donuyor | Basarili | 4096 karakter limiti korundu |
| Sistem | Gemini fallback sayaclari izleniyor | Basarili | Admin stats fallback sayaçlari artti |

**Genel Basari Puani:** `%100`
