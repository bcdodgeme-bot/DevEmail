# Unified Inbox & PIM

A unified email inbox and personal information management system. Pulls in multiple Gmail accounts via API, serves mail from a Stalwart mail server, and provides a single interface for all email, contacts, and calendars.

**Live at:** `https://app.damnitcarl.dev`

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Frontend (TBD)                  │
│              app.damnitcarl.dev                  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              FastAPI Backend                      │
│              Railway (Python)                     │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌────────────────┐ │
│  │   Auth   │  │ Routers  │  │   Services     │ │
│  │  Google  │  │ Messages │  │  Gmail Sync    │ │
│  │  OAuth   │  │ Contacts │  │  Stalwart Sync │ │
│  │  + JWT   │  │ Calendar │  │  Email Send    │ │
│  │          │  │ Accounts │  │                │ │
│  └──────────┘  └──────────┘  └────────────────┘ │
└───────┬──────────────┬──────────────┬───────────┘
        │              │              │
   ┌────▼────┐   ┌─────▼─────┐  ┌────▼──────────┐
   │ Postgres │   │   Redis   │  │   Stalwart    │
   │ Railway  │   │  Railway  │  │ mail.damnit   │
   │          │   │           │  │  carl.dev     │
   │ Users    │   │ Sessions  │  │ Hetzner VPS   │
   │ Messages │   │ Cache     │  │ 5.161.186.236 │
   │ Contacts │   │ Queues    │  │               │
   └──────────┘   └───────────┘  └───────────────┘
```

## Tech Stack

- **Backend:** Python 3.12 / FastAPI
- **Database:** PostgreSQL (Railway) with SQLAlchemy 2.0 async
- **Cache/Queue:** Redis (Railway)
- **Mail Server:** Stalwart (Hetzner VPS)
- **Auth:** Google OAuth + JWT (access + refresh tokens)
- **IMAP:** aioimaplib (async)
- **SMTP:** aiosmtplib (async)

## Project Structure

```
unified-inbox/
├── app/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Settings (env vars)
│   ├── database.py             # SQLAlchemy engine + session
│   ├── redis.py                # Redis connection
│   ├── models/                 # SQLAlchemy ORM models
│   │   ├── user.py             # User + RefreshToken
│   │   ├── account.py          # Linked email accounts
│   │   ├── message.py          # Email messages
│   │   ├── thread.py           # Conversation threads
│   │   ├── contact.py          # Address book
│   │   ├── calendar.py         # Calendars + Events
│   │   ├── folder.py           # Folders / Labels
│   │   ├── signature.py        # Per-account signatures
│   │   ├── attachment.py       # File attachments
│   │   ├── notification.py     # Notification preferences
│   │   └── unsubscribe.py      # Detected unsubscribe links
│   ├── schemas/                # Pydantic request/response models
│   │   ├── auth.py
│   │   ├── account.py
│   │   ├── message.py
│   │   ├── contact.py
│   │   └── calendar.py
│   ├── routers/                # API endpoints
│   │   ├── auth.py             # Google OAuth, token refresh, logout
│   │   ├── accounts.py         # Link/manage email accounts + signatures
│   │   ├── messages.py         # Inbox, threads, compose, search, bulk actions
│   │   ├── contacts.py         # Address book CRUD + search
│   │   ├── calendars.py        # Calendar + event CRUD
│   │   └── health.py           # Health check endpoint
│   ├── services/               # Business logic
│   │   ├── auth.py             # JWT creation, refresh token management
│   │   ├── google_oauth.py     # Google OAuth flow + token refresh
│   │   ├── gmail_sync.py       # Pull mail from Gmail API
│   │   ├── stalwart_sync.py    # Pull mail from Stalwart via IMAP
│   │   └── email_send.py       # Send via Gmail API or Stalwart SMTP
│   └── middleware/
│       └── auth.py             # JWT auth dependency
├── requirements.txt
├── Dockerfile
├── railway.toml
├── .env.example
└── .gitignore
```

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/YOUR_USER/unified-inbox.git
cd unified-inbox
cp .env.example .env
# Edit .env with your actual values
```

### 2. Google Cloud OAuth credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable these APIs:
   - Gmail API
   - Google Calendar API
   - People API (for contacts)
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
5. Application type: **Web application**
6. Authorized redirect URI: `https://app.damnitcarl.dev/api/auth/google/callback`
7. Copy the Client ID and Client Secret into your `.env`

### 3. Railway deployment

1. Push to GitHub
2. In Railway, create a new **App Service** from the GitHub repo
3. Add these environment variables (from `.env.example`):
   - `DATABASE_URL` — from Railway PostgreSQL (use the `postgresql+asyncpg://` format)
   - `REDIS_URL` — from Railway Redis
   - `JWT_SECRET_KEY` — generate with `openssl rand -hex 32`
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI`
4. Add custom domain: `app.damnitcarl.dev`
5. Add a persistent volume mounted at `/data/attachments`

### 4. Database migrations

Run these SQL files against Railway PostgreSQL (via TablePlus):

1. `001_initial_schema.sql` — all tables
2. `002_import_cloze_contacts.sql` — 8,487 contacts from Cloze
3. `003_add_refresh_tokens.sql` — JWT refresh token table

### 5. Local development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## API Reference

Base URL: `https://app.damnitcarl.dev/api`

Interactive docs: `https://app.damnitcarl.dev/api/docs`

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/auth/google/login` | Redirect to Google OAuth |
| GET | `/auth/google/callback` | OAuth callback (creates user + account) |
| POST | `/auth/refresh` | Exchange refresh token for new access token |
| POST | `/auth/logout` | Revoke a refresh token |
| POST | `/auth/logout-all` | Revoke all sessions |
| GET | `/auth/me` | Get current user |

### Accounts
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/accounts` | List linked email accounts |
| POST | `/accounts/stalwart` | Link a Stalwart account |
| GET | `/accounts/{id}` | Get account details |
| PATCH | `/accounts/{id}` | Update account settings |
| DELETE | `/accounts/{id}` | Unlink account |
| GET | `/accounts/{id}/signatures` | List signatures |
| POST | `/accounts/{id}/signatures` | Create signature |
| PUT | `/accounts/{id}/signatures/{sig_id}` | Update signature |
| DELETE | `/accounts/{id}/signatures/{sig_id}` | Delete signature |

### Messages
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/messages/inbox` | Unified inbox (threaded) |
| GET | `/messages/drafts` | Draft messages |
| GET | `/messages/sent` | Sent messages |
| GET | `/messages/trash` | Trashed messages |
| GET | `/messages/threads/{id}` | Full thread with messages |
| PATCH | `/messages/threads/{id}/star` | Toggle thread star |
| PATCH | `/messages/threads/{id}/read` | Mark thread read |
| PATCH | `/messages/threads/{id}/unread` | Mark thread unread |
| PATCH | `/messages/threads/{id}/archive` | Archive thread |
| PATCH | `/messages/threads/{id}/trash` | Trash thread |
| POST | `/messages/threads/{id}/snooze` | Snooze thread |
| PATCH | `/messages/threads/{id}/unsnooze` | Unsnooze thread |
| GET | `/messages/{id}` | Get single message |
| PATCH | `/messages/{id}/star` | Toggle message star |
| PATCH | `/messages/{id}/read` | Mark message read |
| POST | `/messages/compose` | Compose / save draft |
| POST | `/messages/search` | Full-text search |
| POST | `/messages/bulk/read` | Bulk mark read |
| POST | `/messages/bulk/unread` | Bulk mark unread |
| POST | `/messages/bulk/archive` | Bulk archive |
| POST | `/messages/bulk/trash` | Bulk trash |

### Contacts
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/contacts` | List contacts (paginated, searchable) |
| POST | `/contacts` | Create contact |
| GET | `/contacts/{id}` | Get contact detail |
| PUT | `/contacts/{id}` | Update contact |
| DELETE | `/contacts/{id}` | Delete contact |
| PATCH | `/contacts/{id}/favorite` | Toggle favorite |

### Calendars
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/calendars` | List calendars |
| POST | `/calendars` | Create calendar |
| GET | `/calendars/{id}` | Get calendar |
| PATCH | `/calendars/{id}` | Update calendar |
| DELETE | `/calendars/{id}` | Delete calendar |
| GET | `/calendars/events/all` | Events across all calendars |
| GET | `/calendars/{id}/events` | Events for a calendar |
| POST | `/calendars/{id}/events` | Create event |
| GET | `/calendars/{id}/events/{eid}` | Get event |
| PATCH | `/calendars/{id}/events/{eid}` | Update event |
| DELETE | `/calendars/{id}/events/{eid}` | Delete event |

### Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | API + DB + Redis health check |

## Mail Server

Stalwart Mail Server on Hetzner VPS (`5.161.186.236`):

- **Domain:** `mail.damnitcarl.dev`
- **IMAP:** port 993 (TLS)
- **SMTP:** port 465 (TLS), port 25 (inbound)
- **DNS:** MX, SPF, DKIM (Ed25519 + RSA), DMARC, PTR all configured
- **TLS:** Let's Encrypt (auto-renewing)
