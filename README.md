# DraftWeave: Multi-Format Telegram Content Agent with Persistent Memory

DraftWeave is an automated, production-minded **Content Ingestion & Strategy Agent** built to operate via Telegram. It ingests content across multiple formats (**Plain Text**, **Web Article URLs**, and **PDF Documents**), converts and processes them through Large Language Models (NVIDIA Nemotron API primary with Gemini, Groq, and local Ollama fallbacks), applies persistent user-specific **Style Memory**, and logs structured, multi-variant drafts idempotently into **Google Sheets**.

---

## 🌟 Key Features

1. **Multi-Format Content Router**:
   - **Plain Text**: Ingests notes, thoughts, and text snippets. Generates content hashes for duplicate detection.
   - **Web Links (URLs)**: Extracts clean article content using `trafilatura` (stripping ads, navigation bars, and layout noise).
   - **PDF Documents**: Converts complex PDF page layouts into clean, structured Markdown using `microsoft/markitdown`.

2. **Persistent Style Memory**:
   - Uses a local SQLite database (`data/style_memory.db`) to store user-specific persona preferences set via `/setstyle <prompt>`.
   - Dynamic prompt injection ensures all future AI generations match the user's house style.

3. **Multi-Backend LLM Orchestration**:
   - **Primary Cloud Provider**: NVIDIA NIM API (`nvidia/nemotron-3.5-lightning-30b` / `nvidia/nemotron-3-super-120b`).
   - **Secondary Cloud Fallbacks**: Google Gemini (`gemini-1.5-flash`) & Groq (`llama-3.3-70b-versatile`).
   - **Local Fallback**: Ollama hosting `llama3.2:3b` or `gemma:2b` via `http://localhost:11434`.
   - **Structured JSON Engine**: Enforces strict JSON schema validation, automatic retry loops, and strict character limits ($\le 280$ characters for X posts).

4. **Idempotent Google Sheets Storage**:
   - Writes directly to Google Sheets (`gspread`).
   - Checks existing `SourceIdentifier` keys prior to appending, preventing duplicate entries when identical links or text are forwarded.
   - **Style-Aware Idempotency**: Re-submitting content after updating style preferences (`/setstyle`) creates a new row reflecting the updated style.

5. **Containerized Deployment**:
   - Packaged with Docker and orchestrated with `docker-compose`.
   - Includes automated container health checks verifying SQLite database integrity and application uptime.

---

## 🏗️ System Architecture & Data Flow

```
[Telegram User] 
       │ (Sends Text, URL, PDF, or Commands)
       ▼
[Telegram Bot API]
       │ (Long Polling)
       ▼
┌─────────────────────────────────────────────────────────────┐
│ Ingestion Layer & Content Router                            │
│  ├── /start & /setstyle ──► SQLite Style Memory             │
│  ├── Plain Text ──────────► Text Normalizer & Hasher        │
│  ├── Web URL ─────────────► Trafilatura HTML Extractor      │
│  └── PDF Document ────────► MarkItDown PDF-to-Markdown      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ AI Core & LLM Orchestrator                                  │
│  ├── Retrieve User Style Prompt                             │
│  ├── Build System Persona & Input Prompt                    │
│  └── Call LLM Engine (NVIDIA Nemotron / Gemini / Ollama)    │
│  └── Validate Structured JSON Output & Truncate X Draft     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Google Sheets Integration Layer                             │
│  ├── Check Idempotency (SourceIdentifier + Style Hash)      │
│  └── Append Row to 'Content' Worksheet                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 📐 Architectural Rationale: Webhook vs. Long Polling

In this application, **Long Polling** was chosen as the Telegram update mechanism over Webhooks.

| Criteria | Webhook | Long Polling (Chosen) |
| :--- | :--- | :--- |
| **Free-Tier & Cold Starts** | ❌ Fragile. Free hosting platforms (Render, Fly.io) sleep after inactivity. Telegram HTTP POST requests time out before cold starts finish, resulting in lost updates. | ✅ **Resilient**. Connection is initiated from inside the app container, maintaining continuous update retrieval without losing updates during sleep states. |
| **Infrastructure Setup** | ❌ Requires a publicly accessible domain, SSL/TLS certificate, or ngrok tunnel setup during local testing. | ✅ **Zero Setup**. Works behind NATs, firewalls, and Docker networks out of the box with standard outgoing HTTPS connections. |
| **Complexity** | ❌ Requires embedding an HTTP web server (Flask/FastAPI) inside the bot process. | ✅ **Clean & Native**. Uses standard `python-telegram-bot` event-loop polling. |

---

## 📊 Google Sheets Schema

Worksheet Name: `Content`

| Column Index | Column Header | Description |
| :---: | :--- | :--- |
| 1 | `SourceIdentifier` | Unique URL string or SHA-256 content hash (with style tag if customized) |
| 2 | `SubmissionTimestamp` | ISO 8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`) |
| 3 | `ContentType` | Content format tag: `'text'`, `'url'`, or `'pdf'` |
| 4 | `LLMTitle` | Compelling title generated by LLM |
| 5 | `Rationale` | Editorial rationale generated by LLM |
| 6 | `Category` | Content category tag (e.g., `'AI'`, `'Startups'`, `'Productivity'`) |
| 7 | `X_Variant` | Short punchy draft optimized for X / Twitter ($\le 280$ characters) |
| 8 | `LinkedIn_Variant` | Longer professional draft formatted for LinkedIn |

---

## ⚙️ Environment Variables Setup

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

| Variable Name | Description | Example / Default |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Bot API Token from Telegram `@BotFather` | `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ` |
| `GOOGLE_SHEETS_CREDENTIALS_B64` | Base64 encoded Service Account JSON key | `ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCI...` |
| `GOOGLE_SHEETS_CREDENTIALS_JSON` | File path to Service Account JSON key | `credentials.json` |
| `GOOGLE_SHEET_NAME` | Target Google Sheet Name | `DraftWeave Content` |
| `GOOGLE_SHEET_ID` | Target Google Sheet Spreadsheet ID | `1A2b3C4d5E6f7G8h9I0j` |
| `NVIDIA_API_KEY` | NVIDIA NIM API Key (Primary Cloud Provider) | `nvapi-...` |
| `NVIDIA_MODEL` | NVIDIA Model Name | `nvidia/nemotron-3.5-lightning-30b` |
| `GOOGLE_API_KEY` | Google AI Studio API Key (Fallback) | `AIzaSy...` |
| `GROQ_API_KEY` | Groq Cloud API Key (Fallback) | `gsk_...` |
| `OLLAMA_BASE_URL` | Local Ollama Base URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Local Ollama Model Name | `llama3.2:3b` |
| `LLM_PROVIDER` | Active LLM Provider Strategy | `nvidia` (options: `nvidia`, `gemini`, `groq`, `ollama`) |
| `SQLITE_DB_PATH` | Path to SQLite Style Memory DB | `data/style_memory.db` |

---

## 🚀 Quick Start (Docker)

1. **Clone Repository & Configure Environment**:
   ```bash
   git clone <repository_url>
   cd DraftWeave
   cp .env.example .env
   # Edit .env with your TELEGRAM_BOT_TOKEN & Google Sheets Credentials
   ```

2. **Run Application using Docker Compose**:
   ```bash
   docker-compose up --build -d
   ```

3. **Verify Container Health**:
   ```bash
   docker-compose ps
   ```
   *The service status will report `healthy` within 3 minutes.*

4. **Interact via Telegram**:
   - Open Telegram and search for your bot.
   - Send `/start` to view the welcome message.
   - Set a custom style prompt: `/setstyle Write in the style of a witty tech founder with emojis.`
   - Forward any text message, web article URL, or upload a PDF document.
   - Check your Google Sheet to view the structured row entry!

---

## 🧪 Running Unit Tests

Run test discovery across all test modules:
```bash
python -m unittest discover tests
```

---

## 📜 License

MIT License. Designed and built for the Global Placement Program.
