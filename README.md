# SafeAI — LSTT: Lightweight Semantic Trajectory Tracking

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Google Gemini API](https://img.shields.io/badge/Google_Gemini_API-8E75B2?logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![Supabase](https://img.shields.io/badge/Supabase-3FCF8E?logo=supabase&logoColor=white)](https://supabase.com/)
[![n8n](https://img.shields.io/badge/n8n-EA4B71?logo=n8n&logoColor=white)](https://n8n.io/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![ngrok](https://img.shields.io/badge/ngrok-1F1E37?logo=ngrok&logoColor=white)](https://ngrok.com/)
[![Plotly](https://img.shields.io/badge/Plotly-3F4F75?logo=plotly&logoColor=white)](https://plotly.com/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?logo=scikitlearn&logoColor=white)](https://scikit-learn.org/)
[![License](https://img.shields.io/badge/License-Hackathon_Prototype-lightgrey)]()

A lightweight, state-aware AI governance prototype that detects multi-turn "Crescendo Attacks" — jailbreaks that split malicious intent across several seemingly-innocent prompts to evade single-turn safety filters.

---

## 🔴 Try It Live

| | |
|---|---|
| **Mock Chatbot + Dashboard** | `https://safeai-hackattack.streamlit.app/` |
| **Source Code** | `THIS REPOSITORY` |

> **Important caveat before you click:** the frontend above is genuinely always-on (hosted on Streamlit Community Cloud). The **safety plugin (n8n) is not** at this stage temporarily — it runs on the developer's own machine and is only reachable while that machine, Docker, and an ngrok tunnel are actively running. If you try the live link and the dashboard shows "Not enough embedded turns," the backend is very likely offline at that moment. See [Known Limitations](#-known-limitations) below, and coordinate with the team if you need a live backend demo.

---

## 🎯 Problem Solved

Most enterprise AI guardrails evaluate each prompt **in isolation**, like inspecting network packets one at a time. This "context-insensitive" gap lets attackers:

- **Crescendo Attacks** — gradually steer a conversation toward a prohibited topic over several benign-looking turns, none of which individually triggers a filter.
- **Euphemism/metaphor bypasses** — swap a dangerous noun for an innocent-sounding stand-in (e.g. asking to "smuggle sugar" into a country where it's "banned") so token-level filters see harmless words and miss the underlying intent.

Enterprises also **aggressively prune conversation history** sent to safety classifiers to save cost and latency — which is exactly the blind spot these attacks exploit.

## 👥 Target Users

- **Enterprise AI/ML safety teams** deploying internal or customer-facing LLM chatbots who need a lightweight layer between "no monitoring" and "expensive full-history re-analysis on every turn."
- **Security researchers / red teams** evaluating how conversational, trajectory-based attacks evade snapshot-based filters.
- **Hackathon judges and technical reviewers** assessing the feasibility of state-aware, low-cost AI governance architecture.

## 💡 Solution

**LSTT (Lightweight Semantic Trajectory Tracking)** shifts the defense model from static text filtering to dynamic behavioral tracking:

1. Every user message is converted into a semantic embedding (a vector) rather than re-analyzed as raw text on every turn.
2. Each new turn's embedding is compared — via cosine similarity — against a pre-computed "danger zone" anchor representing prohibited topics.
3. The **trend** (is similarity to danger increasing turn-over-turn?), not just a single-point score, determines whether a conversation is escalating.
4. If a request crosses a similarity threshold *and* is trending toward the danger zone, the plugin can flag it — and, in the enforcing configuration, block the request before the underlying LLM ever generates a response.
5. A live dashboard visualizes the conversation's path through semantic space (via PCA-compressed 2D projection) alongside a plotted danger zone, so the trajectory is visible, not just logged.

This keeps compute cost low (geometric math on cached vectors, not repeated full-context LLM safety calls) — meeting the project's zero-budget constraint while closing the context-insensitive gap.

---

## 🏗️ Architecture

```
┌─────────────────┐        ┌──────────────┐        ┌─────────────────────┐
│  Streamlit App   │──────▶│   Supabase    │◀──────│   n8n (local +       │
│  (Mock Gemini     │       │  (Postgres +  │        │   ngrok tunnel)      │
│  chatbot +         │◀──────│   Storage)    │──────▶│   LSTT plugin logic  │
│  dashboard)         │       └──────────────┘        └─────────────────────┘
│  hosted on           │              ▲
│  Streamlit Cloud      │              │
└───────────┬───────────┘              │
            │                          │
            ▼                          │
   ┌──────────────────┐                │
   │  Google Gemini API │───────────────┘
   │  (chat, image gen,   │
   │  embeddings)           │
   └──────────────────────┘
```

- **Frontend:** Streamlit — mock Gemini-style chatbot (text + image input/output) and a security dashboard, both reading/writing Supabase directly.
- **Database & Storage:** Supabase (Postgres `conversations` table + a Storage bucket for uploaded/generated images).
- **Safety Plugin:** n8n workflow — webhook-triggered, fetches unembedded messages, calls Gemini's embedding model, computes trajectory math, writes results back to Supabase.
- **LLM Provider:** Google Gemini API — `gemini-3.5-flash` (text + vision), `gemini-2.5-flash-image` (image generation), `gemini-embedding-001` (embeddings).

---

## ⚠️ Known Limitations

Stated explicitly rather than discovered by a judge mid-demo:

- **Backend is not cloud-hosted.** n8n runs locally via Docker, exposed through a free ngrok tunnel — it needs the developer's machine on to respond. (Render's free tier was tried first; its 512MB RAM is below n8n's own ~1–2GB minimum and caused out-of-memory crashes.)
- **Images bypass trajectory tracking.** Uploaded/generated images are stored and displayed but are not currently embedded or analyzed by the LSTT plugin — only text turns are tracked. Image behaviour tracking will be developed soon.
- **Session-scoped tracking can be evaded across sessions.** An attacker who restarts the conversation (new `session_id`) resets the trajectory. Production use would need a persistent identity (authenticated user ID) to correlate trajectories across sessions.
- **Free-tier Gemini quotas are low and shared per Google Cloud project**, not per API key — rotating keys within the same project does not reset quota.

---

## 🛠️ Maintenance Guide (For Developers)

### Rotating the Gemini API key
The key is stored in **four separate places** — update all of them, or you'll get confusing partial failures (e.g. chat works, plugin silently stops):
1. Local `.streamlit/secrets.toml` → `GEMINI_API_KEY`
2. Streamlit Cloud → App Settings → Secrets → `GEMINI_API_KEY`
3. n8n's HTTP Request node (embedding call) → the key is in the URL query string (`?key=...`), not a stored credential — must click **Publish** again after editing
4. Any local diagnostic scripts that hardcode the key

> If you hit a `429 RESOURCE_EXHAUSTED` and a new key in the *same* Google Cloud project doesn't fix it — quota is tracked per-project, not per-key. Generate the new key under **"Create API key in new project."**

### Starting the local backend for a demo/session
```powershell
docker start n8n          # if not already running (unless-stopped policy keeps it up across reboots)
cd C:\ngrok
.\ngrok.exe http 5678 --url=https://your-dev-domain.ngrok-free.app
```
Confirm the n8n editor loads at your dev domain, and that the workflow shows **Published** with no pending draft changes.

### Common failure patterns and fixes
| Symptom | Cause |
|---|---|
| `NotFound: models/...` | Google renamed/retired a model — re-run the model-listing diagnostic script and update the model string |
| n8n Update node fails with generic `400 Bad Request` | An expression field (URL, filter value) doesn't have its `fx` toggle enabled and is being sent as literal text |
| Dashboard shows all sessions mixed together | `Get many rows` node's `session_id` filter isn't actually active — re-check the `fx` toggle |
| Code node only outputs 1 item despite N items in | Node is set to "Run Once for All Items" instead of iterating with `$input.all()` |

Full troubleshooting table: see `Detailed_Guide.md` → Troubleshooting Checklist.

---

## 🔌 Bringing the n8n Backend Live (For Developers)

The Streamlit frontend is always-on once deployed, but **the LSTT plugin is not** — it runs locally via Docker and is only reachable from the internet while your machine, Docker, and an ngrok tunnel are all active. If a judge (or anyone) is going to try the live link and expects the dashboard/flagging to actually work, do this checklist **before** sharing the link, not after someone reports it's broken.

### One-time setup (only needed once, ever)
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop) and let it finish starting.
2. Create a persistent volume so workflows survive restarts:
   ```
   docker volume create n8n_data
   ```
3. Run n8n with `--restart unless-stopped` so it comes back up automatically after a reboot:
   ```powershell
   docker run -d --restart unless-stopped --name n8n `
     -p 5678:5678 `
     -v n8n_data:/home/node/.n8n `
     -e N8N_BASIC_AUTH_ACTIVE=true `
     -e N8N_BASIC_AUTH_USER=admin `
     -e N8N_BASIC_AUTH_PASSWORD=your-own-password-here `
     -e N8N_WEBHOOK_URL=https://your-dev-domain.ngrok-free.app `
     n8nio/n8n
   ```
4. Sign up at [ngrok.com](https://ngrok.com), install the app, run `ngrok config add-authtoken YOUR_TOKEN`, and claim your **one free permanent dev domain** under the dashboard's **Domains** page — this keeps your public URL stable across every future restart, so you never have to update Streamlit's secrets again after the first time.

### Every time you need the backend live (e.g. before a demo or when a judge is testing)
```powershell
# 1. Make sure Docker Desktop is open, then:
docker start n8n

# 2. In a separate terminal, start the tunnel (leave this window open):
cd C:\ngrok
.\ngrok.exe http 5678 --url=https://your-dev-domain.ngrok-free.app
```
Then confirm:
- `docker ps` shows `n8n` with status `Up`.
- Opening `https://your-dev-domain.ngrok-free.app` in a browser shows the n8n login screen.
- In the n8n editor, the **"LSTT Analysis Plugin"** workflow shows **Published** with no pending unpublished changes (edits sit as a draft until you click **Publish** again — see `Detailed_Guide.md` Part 8.6).
- `N8N_WEBHOOK_URL` in Streamlit Cloud's secrets matches your current ngrok dev domain exactly.

### Shutting it down afterward
```
docker stop n8n
```
(Safe to do — your workflows and data persist in the named volume. Closing the ngrok terminal window also stops the tunnel.)

Full walkthrough with exact clicks for every step above: see [`Detailed_Guide.md`](./Detailed_Guide.md) → Part 7.

---

## 🚀 Implementation Guide (For Judges — Run This Yourself)

You have two options:

### Option A — Use the live Streamlit link (fastest)
Click the link in [Try It Live](#-try-it-live). You can chat and generate/upload images immediately. **Note:** the LSTT dashboard/flagging only works while the team's local n8n backend and ngrok tunnel are active — ask the team to confirm this before you test that part.

### Option B — Run the full stack yourself (recommended for a thorough review)
Follow [`Detailed_Guide.md`](./Detailed_Guide.md) end to end — it's written for someone with no prior setup, covering:
1. Account creation (GitHub, Supabase, Gemini API key, ngrok)
2. Cloning the repo and setting up secrets
3. Creating the Supabase table + Storage bucket
4. Running the Streamlit app locally
5. Running n8n via Docker + ngrok and building the workflow
6. Verifying the full loop end-to-end

Approximate setup time following the guide: 45–90 minutes for a first-time setup.

---

## 📁 Repository Structure

```
├── app.py                   # Mock chatbot (text + image chat, Gemini API calls)
├── pages/
│   └── 1_Dashboard.py       # LSTT security dashboard (trajectory graph, image gallery)
├── requirements.txt         # Python dependencies
├── .gitignore
├── Execution_Plan.md        # High-level phased build plan
├── Detailed_Guide.md        # Full click-by-click setup, deployment & troubleshooting guide
└── README.md                # This file
```

---

## 📄 License

Hackathon prototype — not licensed for production use. Built as a zero-budget proof of concept.
