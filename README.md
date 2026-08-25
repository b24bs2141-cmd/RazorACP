# RazorACP — India's First ACP-Compliant Agentic Payment System

**Razorpay AI Buildathon 2026 — Track 01: AI Growth & Agentic Commerce**

## The Problem

Every major Western merchant — on Shopify, Amazon, eBay — can now be purchased from by an AI agent. ChatGPT can browse a catalog, pick a product, and complete a payment autonomously using the **Agentic Commerce Protocol (ACP)**, developed by OpenAI and Stripe.

**No Indian merchant can do this today.**

There is no ACP-compliant Payment Service Provider (PSP) for India. Razorpay processes ₹28.92 trillion in monthly UPI transactions — but none of that infrastructure speaks the protocol that AI agents use to transact. Indian merchants are invisible to the agentic commerce ecosystem.

**This is the gap RazorACP fills.**

## What RazorACP Does

RazorACP is an ACP-compliant PSP adapter built on top of Razorpay's test-mode API. It makes any Indian merchant transactable by AI agents — with no changes to the merchant's existing Razorpay setup.

An AI agent (Gemini, Claude, GPT) can:

- ✅ Discover a merchant's product catalog
- ✅ Make an autonomous purchase decision based on a user's goal and budget
- ✅ Request a Shared Payment Token (SPT) from the PSP
- ✅ Create a checkout session with the merchant
- ✅ Complete payment via Razorpay — with a real order ID
- ✅ Log every action in a tamper-evident audit trail

No human clicks anything after the agent starts. Every money action is explainable, bounded, and gated.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    AI BUYER AGENT                        │
│              (Gemini 3.6 Flash via Google API)           │
└────────────────────────┬────────────────────────────────┘
                         │ ACP Protocol
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
   GET /products   POST /checkouts  POST /checkouts
                                    /{id}/complete
          │              │              │
┌─────────▼──────────────▼──────────────▼─────────┐
│              MERCHANT API (Port 8000)             │
│           FastAPI — Desi Bazaar Demo Store        │
│  • Product Feed Spec (ACP)                        │
│  • Checkout Session Spec (ACP)                    │
│  • In-memory session store with audit trail       │
└──────────────────────┬──────────────────────────┘
                       │ POST /v1/charges
                       ▼
┌──────────────────────────────────────────────────┐
│           RAZORPAY PSP ADAPTER (Port 8001)        │
│        FastAPI — ACP-Compliant PSP Layer          │
│  • POST /v1/tokens   → Issues Shared Payment      │
│                        Token (SPT)                │
│  • POST /v1/charges  → Creates Razorpay Order     │
│  • Token validation  → Amount bounds, expiry,     │
│                        single-use enforcement     │
└──────────────────────┬──────────────────────────┘
                       │ Razorpay Python SDK
                       ▼
┌──────────────────────────────────────────────────┐
│           RAZORPAY TEST-MODE API                  │
│         Real order created. Real order ID.        │
│         Verifiable on dashboard.razorpay.com      │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│           DECIDE SERVICE (Port 8002)              │
│     FastAPI — Gemini AI Decision Endpoint         │
│  • Accepts: user goal + budget + product list     │
│  • Returns: product_id + quantity + reason        │
│  • Used by: browser-based frontend agent          │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│           FRONTEND (Port 5500)                    │
│     HTML/CSS/JS — RazorACP Demo Dashboard         │
│  • Live agent log with step-by-step flow          │
│  • Product catalog with AI selection highlight    │
│  • Real-time audit trail                          │
│  • Session stats (orders created, value processed)│
└──────────────────────────────────────────────────┘
```

## ACP Compliance

RazorACP implements all three ACP specifications:

| Spec | Endpoint | Description |
|------|----------|-------------|
| Product Feed Spec | `GET /products` | Structured catalog with SKU, price, inventory, category |
| Agentic Checkout Spec | `POST /checkouts` | Stateful checkout session with tax, total, bounds check |
| Delegated Payment Spec | `POST /v1/tokens` + `POST /v1/charges` | SPT issuance and single-use token enforcement |

### Track 01 Requirements — All Met ✅

| Requirement | Implementation |
|-------------|-----------------|
| Every money action explainable | Every decision logged with timestamp, reason, and actor |
| Bounded | SPT enforces `max_amount` — agent cannot exceed user's budget |
| Gated | Token is single-use, expires in 5 minutes, tied to `buyer_agent_id` |
| Audit trail | Full session audit trail returned on every checkout GET |
| One failure handled gracefully | Token expiry, amount exceeded, and invalid token all return structured errors |

## Tech Stack

| Layer | Technology |
|-------|------------|
| Merchant API | Python 3.11 + FastAPI |
| PSP Adapter | Python 3.11 + FastAPI + Razorpay Python SDK |
| AI Buyer Agent | Google Gemini 3.6 Flash (google-genai SDK) |
| Decide Service | Python 3.11 + FastAPI |
| Frontend | Vanilla HTML/CSS/JS |
| Payment Rail | Razorpay Test-Mode API |
| Protocol | ACP v2026-04-17 (OpenAI + Stripe) |

## Project Structure

```
razorpay/
├── merchant/
│   └── main.py          # ACP Merchant API (Product Feed + Checkout)
├── psp/
│   └── main.py          # Razorpay ACP PSP Adapter (Token + Charge)
├── agent/
│   ├── buyer.py         # CLI AI Buyer Agent (Gemini)
│   └── decide.py        # Decide microservice for browser frontend
├── frontend/
│   └── index.html       # RazorACP Demo Dashboard
├── data/
│   └── products.json    # Desi Bazaar product catalog
├── .env                 # API keys (not committed)
└── README.md
```

## Quick Start

### Prerequisites

- Python 3.11+
- Razorpay Test Mode API Keys
- Google Gemini API Key
- Pip

### Installation

```bash
git clone https://github.com/b24bs2141-cmd/RazorACP.git
cd RazorACP
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the root:

```env
RAZORPAY_KEY_ID=your_razorpay_key_id
RAZORPAY_KEY_SECRET=your_razorpay_key_secret
GOOGLE_API_KEY=your_gemini_api_key
```

### Run All Services

```bash
# Terminal 1: Merchant API
python merchant/main.py

# Terminal 2: PSP Adapter
python psp/main.py

# Terminal 3: Decide Service
python agent/decide.py

# Terminal 4: Frontend (static server)
python -m http.server 5500 --directory frontend
```

Visit `http://localhost:5500` to see the dashboard.

### Run AI Agent

```bash
python agent/buyer.py --goal "Buy a phone under ₹5000" --merchant-url http://localhost:8000
```

## API Endpoints

### Merchant API (Port 8000)

- `GET /products` — Get product catalog
- `POST /checkouts` — Create checkout session
- `GET /checkouts/{id}` — Get checkout details with audit trail
- `POST /checkouts/{id}/complete` — Complete checkout with SPT

### PSP Adapter (Port 8001)

- `POST /v1/tokens` — Issue Shared Payment Token (SPT)
- `POST /v1/charges` — Create charge with SPT validation

### Decide Service (Port 8002)

- `POST /decide` — AI decision on product selection

## License

MIT License — See LICENSE file for details.

---

Built with ❤️ for Razorpay AI Buildathon 2026
