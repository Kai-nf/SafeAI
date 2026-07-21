
# Execution Plan: Enterprise AI Governance Plugin (LSTT Prototype)

## Project Overview
This execution plan details the step-by-step development of a prototype for a Lightweight Semantic Trajectory Tracking (LSTT) system. The project consists of two main components:
1.  **Mock Gemini Chatbot:** A functional, simulated environment mimicking a standard AI interface to serve as the testbed.
2.  **LSTT Analysis Plugin:** The core product—a backend integration built with n8n that monitors conversation history, performs semantic trajectory tracking, and visualizes intent drift toward prohibited topics.

**Objective:** To demonstrate state-aware intent governance capable of mitigating multi-turn "Crescendo Attacks" with zero projected budget.

---

## Phase 1: Environment Setup & Tool Selection

Given the constraint of zero cost, we will utilize open-source and free-tier tools to build the architecture.

### Tool Stack
*   **Mock Chatbot Frontend:** Streamlit (Python) - Fast, free, and excellent for rapidly building AI chat interfaces.
*   **Database:** Supabase (Free Tier, hosted Postgres) - Replaces the local SQLite file so both the Mock Chatbot and the n8n plugin can read/write the *same* conversation history over the network, from anywhere, without either service needing to be co-located. Supabase also gives you the `pgvector` extension, which means embedding storage and similarity math can eventually live in the database itself.
*   **Workflow Automation / Integration (The "Plugin"):** n8n (Community Edition / Self-hosted or Free Cloud Tier) - Will handle the logic flow, database querying, and API routing.
*   **LLM & Embedding Engine:** Google Gemini API (Free Tier) - Used for both generating chatbot responses and creating the text embeddings needed for trajectory analysis. The chatbot uses the current unified `google-genai` SDK (the older `google-generativeai` package is deprecated), with `gemini-3.5-flash` for text and image-input understanding, and `gemini-2.5-flash-image` ("Nano Banana," free-tier) for image generation.
*   **Image Storage:** Supabase Storage (same free project as the database) - Holds uploaded and AI-generated images as files, referenced by URL from the `conversations` table rather than storing binary data directly in Postgres.
*   **Visualization Engine:** Plotly (via Streamlit) to display the semantic map, querying data live from Supabase.
*   **Hosting:** Streamlit Community Cloud (frontend, always-on) + n8n run locally via Docker and exposed publicly through an ngrok tunnel (backend). n8n needs more RAM (1–2GB) than free cloud web-service tiers typically provide (e.g. Render's free tier gives 512MB, which isn't enough and causes out-of-memory crashes), so it runs on your own machine instead, active whenever you're building or demoing.

---

## Phase 2: Building the Mock Gemini Chatbot

The goal here is to create a realistic testing environment that captures user input, generates an AI response, and logs the interaction.

### Step 2.1: Database Configuration (Supabase)
1.  Create a free Supabase project at [supabase.com](https://supabase.com). Note down the **Project URL** and the **anon/public API key** (Settings → API) — you'll need these in both Streamlit and n8n.
2.  In the Supabase SQL Editor, create a table named `conversations`:
    ```sql
    create table conversations (
      id bigint generated always as identity primary key,
      session_id text not null,
      timestamp timestamptz default now(),
      role text not null,              -- "user" or "model"
      content text not null,
      content_type text default 'text', -- 'text', 'image_input', or 'image_output'
      image_url text,                  -- public Storage URL, only set on image rows
      embedding_vector jsonb,          -- stores the generated coordinates later
      flagged boolean default false    -- set by the n8n plugin on high-risk detection
    );
    ```
3.  (Optional but recommended) Enable the `pgvector` extension (Database → Extensions → search "vector") if you later want to store `embedding_vector` as a native `vector` type and run similarity queries directly in SQL instead of in n8n's Code node.
4.  Because Supabase is a hosted service reachable over HTTPS, both the Streamlit app and the n8n workflow can talk to the *same* live database simultaneously — this is what makes Step 3.1's webhook trigger reliable, since n8n no longer needs file-level access to a local `.db` file.
5.  For the hackathon demo, leave Row Level Security (RLS) off on this table so the Streamlit anon key and n8n can both read/write freely. Note in your pitch that production use would require RLS policies.
6.  Create a Storage bucket to hold actual image files (the table only stores a URL, not the image bytes): click **Storage** in the left sidebar → **"New bucket"** → name it `conversation-images` → toggle **Public bucket** ON (acceptable for a demo; production would use signed URLs and RLS instead) → **"Create bucket"**.
7.  **Important scope note:** `content_type` exists so the n8n plugin (Phase 3) can filter to `content_type = text` when fetching rows to embed. Images are not currently run through LSTT's semantic trajectory tracking — an uploaded or generated image is an unmonitored channel relative to the text-based danger-zone detection. This is worth stating explicitly as a known limitation / future-work item in your pitch, rather than leaving it implicit.

### Step 2.2: Frontend Development (Streamlit)
1.  Set up a Python virtual environment and install dependencies (`streamlit`, `google-generativeai`, `supabase`).
2.  Build the chat interface using `st.chat_message` and `st.chat_input`.
3.  Initialize the Supabase client once at the top of the app, using `st.secrets` to hold the URL and API key (see Phase 6 for how secrets work once deployed):
    ```python
    from supabase import create_client
    supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    ```
4.  **Integration:**
    *   When the user submits a prompt, capture the text.
    *   Call the Gemini API (using your free API key) to get a response.
    *   *Crucially:* Write both the user prompt and the model response to the `conversations` table in Supabase under the current `session_id`, e.g. `supabase.table("conversations").insert({...}).execute()`.
    *   Immediately after inserting the user's message, call the n8n webhook (Step 3.1) so the plugin can process it right away.
5.  **Multimodal support (image input and image output):**
    *   Add a `st.file_uploader` so a user can attach an image; pass it alongside the text prompt into `generate_content()` so Gemini can see and reason about it.
    *   Add a toggle for "generate an image instead of text," which calls the image-generation model (`gemini-2.5-flash-image`) with `response_modalities=["IMAGE"]` instead of the text model.
    *   Any image involved (uploaded or generated) gets uploaded to the `conversation-images` Storage bucket, and its public URL is saved in the `image_url` column of the corresponding `conversations` row, with `content_type` set to `image_input` or `image_output` accordingly.

---

## Phase 3: Developing the LSTT "Plugin" Logic (n8n & Gemini API)

This is the core of the hackathon pitch. The n8n workflow will act as the middleware that monitors the database.

### Step 3.1: n8n Workflow Trigger
1.  Set up an n8n workflow.
2.  **Trigger:** Use a "Schedule" node (e.g., run every 10 seconds) OR set up a Webhook in n8n that your Streamlit app calls immediately after saving a new user message to Supabase. (Webhook is preferred for lower latency). Because both apps talk to Supabase over the internet rather than a local file, this webhook works the same way whether n8n is running on `localhost` or reached through the ngrok tunnel (see Phase 5) — only the URL changes.

### Step 3.2: Fetching Context & Generating Embeddings
1.  **Supabase Node:** Configure this node (n8n has a built-in Supabase integration — just supply your Project URL and API key as credentials) to read the latest turns (e.g., the last 5 user messages) for the active `session_id` where `embedding_vector` is null **and** `content_type` equals `text`. The `content_type` filter is required now that image rows exist in the table — an image row's `content` field holds a caption/prompt rather than the full conversational text, and feeding it into the embedding step would quietly corrupt the trajectory math rather than fail loudly.
2.  **HTTP Request Node (Gemini Embedding API):**
    *   Send the newly fetched user text to the Gemini embedding model (e.g., `text-embedding-004`).
    *   Retrieve the mathematical vector representation of the text.
3.  **Supabase Node (Update):** Write the returned vector back into the `embedding_vector` column for that specific message row.

### Step 3.3: The LSTT Math & Logic (The "Brain")
1.  **Code Node (JavaScript/Python in n8n):** This node performs the trajectory calculation.
    *   Pull the sequence of vectors for the current session.
    *   Calculate the Cosine Similarity or Euclidean Distance between the latest prompt's vector and a pre-defined set of "Danger Zone" anchor vectors (e.g., you will need to pre-generate vectors for phrases like "how to build a bomb" or "explicit content").
    *   **Calculate Trajectory:** Calculate the *delta* (change in distance) between Turn N-1 and Turn N relative to the Danger Zone. Is the user getting mathematically closer to the prohibited topic?

### Step 3.4: Action & Intervention
1.  **If Threshold Exceeded (High Risk):**
    *   The n8n workflow triggers an alert.
    *   It updates the `flagged` column for that row directly in Supabase via the Supabase node.
    *   (Optional for Demo): It can send a webhook back to Streamlit to instantly terminate the session and display a "Safety Violation" warning. Since Streamlit can also poll or subscribe to Supabase directly, this webhook is a nice-to-have rather than the only path — the dashboard will pick up the `flagged` change on its next query regardless.
2.  **If Safe:** Workflow terminates silently.

---

## Phase 4: Visualizing the Semantic Trajectory

Judges need to *see* the math working. You will build a dashboard that updates in real-time.

### Step 4.1: Building the Trajectory Graph
1.  Create a separate page or a side-panel in your Streamlit app for the "Admin/Security Dashboard".
2.  **Data Extraction:** Query Supabase (e.g., `supabase.table("conversations").select("*").eq("session_id", session_id).order("timestamp").execute()`) for the sequence of `embedding_vectors` in a given session. Because Supabase is a live network database, you can also set the dashboard to auto-refresh every few seconds (e.g., `st.rerun()` on a timer) so it stays current even though the plugin runs in a separate n8n process.
3.  **Dimensionality Reduction:** High-dimensional vectors (like those from Gemini) cannot be plotted on a 2D graph. Use Principal Component Analysis (PCA) or t-SNE (via Python's `scikit-learn` library) to compress the 768-dimensional vectors down to X and Y coordinates.
4.  **Plotly Integration:**
    *   Plot the X, Y coordinates on a 2D scatter plot using Plotly (`st.plotly_chart`).
    *   Draw lines connecting Turn 1 -> Turn 2 -> Turn 3 to show the *path*.
    *   Plot a large, red "Danger Zone" circle on the graph representing the prohibited concepts.
    *   As the user types in the mock chat, the graph should dynamically update, showing their conversational dot moving closer to or further from the red zone.
5.  **Image gallery:** Below the trajectory chart, query the same session's rows for any with a non-null `image_url` and display them with `st.image()` in a small grid, captioned by `content_type` (`image_input` vs `image_output`). This makes the unmonitored-image gap (see Phase 3.2) visible to judges rather than hidden — they can see an image was shared in the session even though it wasn't plotted on the trajectory graph.

---

## Phase 5: Deploying the Frontend & Running the Backend

Streamlit Cloud can run the frontend "always on" for free. n8n is a different story: it needs more RAM (1–2GB, per n8n's own documentation) than free cloud web-service tiers typically provide — Render's free tier, for example, gives only 512MB, which causes n8n to crash with an out-of-memory error during startup regardless of which database it's pointed at. Rather than pay for a bigger server, n8n runs locally via Docker and is exposed with a free ngrok tunnel whenever it's needed for building or demoing.

### Step 6.1: Deploy the Streamlit Frontend (Streamlit Community Cloud — Free)
1.  Push your project (the Streamlit app + `requirements.txt`) to a public or private GitHub repo. `requirements.txt` should include `streamlit`, `google-genai`, `supabase`, `plotly`, `scikit-learn`, `pillow`.
2.  Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub, and click "New app," pointing it at your repo and the main `.py` file.
3.  **Secrets:** In the app's Settings → Secrets, add your credentials in TOML format so they're never hardcoded in the repo:
    ```toml
    SUPABASE_URL = "https://xxxx.supabase.co"
    SUPABASE_KEY = "your-anon-key"
    GEMINI_API_KEY = "your-gemini-key"
    N8N_WEBHOOK_URL = "https://your-name.ngrok-free.app/webhook/lstt"
    ```
4.  Deploy. Streamlit Cloud will rebuild automatically on every push to your repo, so updates during the hackathon are just a `git push` away — no manual redeploy step.

### Step 6.2: Run the n8n Backend Locally, Exposed via ngrok
1.  Install Docker Desktop and run n8n in a container with a named volume, so workflows persist across restarts:
    ```
    docker volume create n8n_data
    docker run -d --restart unless-stopped --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n -e N8N_BASIC_AUTH_ACTIVE=true -e N8N_BASIC_AUTH_USER=admin -e N8N_BASIC_AUTH_PASSWORD=your-password n8nio/n8n
    ```
2.  Install ngrok and claim the one free permanent **dev domain** every free account is automatically given — this keeps your public URL stable across restarts, unlike a random tunnel URL.
3.  Start the tunnel: `ngrok http 5678 --url=https://your-name.ngrok-free.app`.
4.  In the n8n editor (`localhost:5678` or the ngrok URL), add your Supabase and Gemini credentials and build the workflow from Phase 3 — the Webhook node exposes a path like `/webhook/lstt-trigger`, which combined with your ngrok domain becomes the full public webhook URL.
5.  Copy that webhook URL into Streamlit's secrets (`N8N_WEBHOOK_URL`, both locally and on Streamlit Cloud) so the deployed frontend can reach the locally-running backend.
6.  **Known limitation, stated plainly:** this backend is only reachable while your computer, Docker, and the ngrok tunnel are all running — it is not "walk away and it stays live" the way Streamlit Cloud is. That's an acceptable trade-off for a hackathon demo (you control when you present) but is worth noting explicitly to judges as a known constraint of the zero-budget prototype, with "a small always-on VPS with adequate RAM" as the natural next step for a production version.
7.  Free ngrok tunnels inject a browser-warning interstitial on HTML-looking traffic, which can silently block the automated webhook call from Streamlit. Add a `ngrok-skip-browser-warning: true` header to that request in `app.py` to avoid this.

### Step 6.3: Verify the End-to-End Loop
1.  With Docker and ngrok both running, open your live Streamlit URL, send a test message, and confirm a new row appears in the Supabase `conversations` table.
2.  Confirm the n8n workflow fires (check the "Executions" tab in the local n8n editor) and writes an `embedding_vector` back to that row.
3.  Confirm the dashboard page picks up the new vector and plots it — this proves the full loop (Streamlit Cloud → Supabase → local n8n via ngrok → Supabase → Streamlit dashboard) works end to end, with only the backend depending on your machine being on.

---

## Phase 6: Demo Execution Strategy for the Hackathon

To win, structure your live demo as follows:

1.  **The Setup:** Briefly explain the "Context-Insensitive Gap" (the vulnerability of snapshot filters) and introduce LSTT.
2.  **The Baseline Test (Safe):** Show a normal conversation in the mock Gemini app (e.g., asking about software engineering). Show the dashboard graph moving safely around the neutral zone.
3.  **The Crescendo Attack (The Hack):**
    *   Start a new session.
    *   Begin with an innocent prompt related to a prohibited topic (e.g., "What is the chemical composition of fertilizer?").
    *   Slowly escalate over 3-4 turns toward a dangerous request (e.g., "How can I maximize its explosive yield?").
4.  **The Reveal:** Switch to the dashboard. Show the judges the line graph charting a direct, accelerating trajectory toward the "Danger Zone."
5.  **The Intervention:** Show how your n8n plugin detected the velocity and automatically flagged/blocked the final prompt *before* the LLM could generate a harmful response, proving the viability of state-aware governance.

---

## Phase 7: Maintenance — Rotating the Gemini API Key

Free-tier Gemini keys hit daily/per-minute quota limits (see Phase 2 and 3's known 404/429 issues), and you may also generate a fresh key if you suspect the old one leaked or want a clean quota reset. Because this project calls the Gemini API from **two separate places** — the Streamlit app and the n8n workflow — a new key has to be updated in **every** place it's referenced, or you'll get inconsistent behavior (e.g., chat replies work but the LSTT plugin silently fails, or vice versa).

### Every location that stores the Gemini API key
1. **Local secrets file** — `.streamlit/secrets.toml` → `GEMINI_API_KEY = "..."` (used when running `streamlit run app.py` on your own machine).
2. **Streamlit Cloud secrets** — your deployed app's Settings → Secrets panel → `GEMINI_API_KEY = "..."` (used by the live, deployed frontend — this is a *separate* copy from your local file and does not sync automatically).
3. **n8n's HTTP Request node ("Embedding" call)** — the key is embedded directly in the URL's query string (`?key=...`), not stored as a reusable n8n credential. This means it must be edited inside the node itself, not in a central credentials list.
4. **Any local diagnostic/test scripts** you've created (e.g. a `list_models.py` used to check available models) — if these hardcode the key rather than reading from secrets, they'll also need manual updates.

A key rotated in only one or two of these will produce confusing, partial failures — for example, the chatbot replying normally while the LSTT plugin quietly stops embedding new messages, since Streamlit and n8n fail independently and neither surfaces the other's errors. Treat key rotation as a single checklist covering all four locations, done in one sitting, followed by an end-to-end test (Phase 5's Step 6.3 verification) to confirm nothing was missed.
    