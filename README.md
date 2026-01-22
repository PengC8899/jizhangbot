# HuiYing Ledger Platform V3 (Commercial Enhanced)

This is the V3 implementation of the HuiYing Ledger Platform, featuring dynamic multi-bot management, independent fee templates, and high-concurrency webhook architecture.

## 🚀 Key Features

1.  **Dynamic Bot Management**: Add/Start/Stop bots via Admin API without restarting the system.
2.  **Independent Fee/Exchange Templates**: Each bot can have unique fee percentages and exchange rates (Group > Bot > System).
3.  **Excel Export**: Commercial-grade financial reporting using `openpyxl`.
4.  **High Concurrency Webhook**: Single-process async architecture using `python-telegram-bot` v20+ and FastAPI.
5.  **Docker & Nginx**: Ready-to-deploy stack with reverse proxy configuration.

## 🛠 Project Structure

```
/
├── app/
│   ├── main.py              # FastAPI Entry Point
│   ├── core/
│   │   ├── bot_manager.py   # Dynamic Bot Manager (Singleton)
│   │   ├── config.py        # Environment Config
│   │   └── database.py      # Async SQLAlchemy
│   ├── models/              # Database Models (Bot, Templates, Transactions)
│   ├── api/                 # REST Endpoints (Admin, Webhook)
│   ├── bot/                 # Telegram Bot Logic (Handlers)
│   └── services/            # Business Logic (Export, Config)
├── docker/                  # Docker Configs
│   └── nginx/
│       └── nginx.conf
├── docker-compose.yml       # Deployment Stack
└── requirements.txt         # Dependencies
```

## ⚡ Quick Start

### 1. Environment Setup

Create a `.env` file (already included in example):
```env
PROJECT_NAME="HuiYing Ledger Platform V3"
DOMAIN=api.yourdomain.com
SECRET_KEY=your_secret_key
TG_MODE=webhook
DATABASE_URL=sqlite+aiosqlite:///./huiying.db
```

### 2. Run with Docker

```bash
docker-compose up -d --build
```

### 3. Add a New Bot (Online)

Use the Admin API to register a new bot. The system will automatically validate the token, save it, and start the bot instance without downtime.

**POST** `/admin/bot/create`

```json
{
  "token": "123456789:ABCDefGhIjkLmNoPqRsTuVwXyZ",
  "name": "MyNewBot"
}
```

### 4. Excel Export

Export daily ledger for a specific group:

**GET** `/admin/group/{chat_id}/export?date=2026-01-22`

## 🧠 Architecture Details

-   **BotManager**: A singleton that manages a dictionary of active `Application` instances. It allows `start_bot(token)` to be called at runtime.
-   **Webhook Routing**: FastAPI receives the webhook at `/telegram/webhook/{bot_id}` and routes the update to the correct `Application` instance in memory.
-   **Security**: Uses `X-Telegram-Bot-Api-Secret-Token` to verify requests come from Telegram.

## 📝 License

Proprietary Software.
