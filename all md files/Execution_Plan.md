
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
*   **LLM & Embedding Engine:** Google Gemini API (Free Tier) - Used for both generating chatbot responses and creating the text embeddings needed for trajectory analysis.
*   **Visualization Engine:** Plotly (via Streamlit) to display the semantic map, querying data live from Supabase.
*   **Hosting:** Streamlit Community Cloud (frontend) + Render or Railway free tier (n8n backend) - so the whole stack runs online continuously instead of on your local machine.

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
      embedding_vector jsonb,          -- stores the generated coordinates later
      flagged boolean default false    -- set by the n8n plugin on high-risk detection
    );
    ```
3.  (Optional but recommended) Enable the `pgvector` extension (Database → Extensions → search "vector") if you later want to store `embedding_vector` as a native `vector` type and run similarity queries directly in SQL instead of in n8n's Code node.
4.  Because Supabase is a hosted service reachable over HTTPS, both the Streamlit app and the n8n workflow can talk to the *same* live database simultaneously — this is what makes Step 3.1's webhook trigger reliable, since n8n no longer needs file-level access to a local `.db` file.
5.  For the hackathon demo, leave Row Level Security (RLS) off on this table so the Streamlit anon key and n8n can both read/write freely. Note in your pitch that production use would require RLS policies.

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

---

## Phase 3: Developing the LSTT "Plugin" Logic (n8n & Gemini API)

This is the core of the hackathon pitch. The n8n workflow will act as the middleware that monitors the database.

### Step 3.1: n8n Workflow Trigger
1.  Set up an n8n workflow.
2.  **Trigger:** Use a "Schedule" node (e.g., run every 10 seconds) OR set up a Webhook in n8n that your Streamlit app calls immediately after saving a new user message to Supabase. (Webhook is preferred for lower latency). Because both apps now talk to Supabase over the internet rather than a local file, this webhook works identically whether n8n and Streamlit are running on your laptop or fully deployed online (see Phase 6).

### Step 3.2: Fetching Context & Generating Embeddings
1.  **Supabase Node:** Configure this node (n8n has a built-in Supabase integration — just supply your Project URL and API key as credentials) to read the latest turns (e.g., the last 5 user messages) for the active `session_id` where `embedding_vector` is null.
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

---

## Phase 5: Deploying Frontend & Backend Online

Running everything locally means restarting Streamlit and n8n every time you close your laptop or the process crashes. Deploying both online keeps the whole stack "always on" for the demo (and for judges to poke at afterward), and it's the natural payoff of moving to Supabase, since both services now just need internet access to the same database — not to each other's local filesystem.

### Step 6.1: Deploy the Streamlit Frontend (Streamlit Community Cloud — Free)
1.  Push your project (the Streamlit app + `requirements.txt`) to a public or private GitHub repo. `requirements.txt` should include `streamlit`, `google-generativeai`, `supabase`, `plotly`, `scikit-learn`.
2.  Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub, and click "New app," pointing it at your repo and the main `.py` file.
3.  **Secrets:** In the app's Settings → Secrets, add your credentials in TOML format so they're never hardcoded in the repo:
    ```toml
    SUPABASE_URL = "https://xxxx.supabase.co"
    SUPABASE_KEY = "your-anon-key"
    GEMINI_API_KEY = "your-gemini-key"
    N8N_WEBHOOK_URL = "https://your-n8n-instance/webhook/xxxx"
    ```
4.  Deploy. Streamlit Cloud will rebuild automatically on every push to your repo, so updates during the hackathon are just a `git push` away — no manual redeploy step.

### Step 6.2: Deploy the n8n Backend (Render or Railway — Free Tier)
1.  Both Render and Railway offer a one-click "Deploy n8n" template (search "n8n" in their template marketplaces), which spins up n8n as a persistent web service with a public HTTPS URL.
2.  Set the required environment variables on the hosting platform (n8n will prompt for these): `N8N_BASIC_AUTH_ACTIVE`, `N8N_BASIC_AUTH_USER`, `N8N_BASIC_AUTH_PASSWORD` (to keep your workflow editor from being publicly open), and `WEBHOOK_URL` (set to the public URL Render/Railway assigns you).
3.  Once deployed, open the hosted n8n editor, add your Supabase and Gemini credentials (Settings → Credentials), and rebuild the workflow from Phase 3 — the Webhook node will now expose a permanent public URL like `https://your-app.onrender.com/webhook/lstt-trigger`.
4.  Copy that webhook URL into your Streamlit app's secrets (`N8N_WEBHOOK_URL`) so the deployed frontend can trigger the deployed backend.
5.  **Free-tier caveat:** Render's free web services spin down after ~15 minutes of inactivity and take a few seconds to "wake up" on the next request — fine for a live demo where you're actively clicking, but worth mentioning to judges if there's a cold-start delay. Railway's free tier has a monthly usage cap instead of spin-down, so pick whichever trade-off suits your demo timing better.

### Step 6.3: Verify the End-to-End Loop
1.  Open your live Streamlit URL, send a test message, and confirm a new row appears in the Supabase `conversations` table.
2.  Confirm the deployed n8n workflow fires (check the "Executions" tab in the n8n editor) and writes an `embedding_vector` back to that row.
3.  Confirm the dashboard page picks up the new vector and plots it — this proves the full loop (Streamlit → Supabase → n8n → Supabase → Streamlit dashboard) works entirely online, with nothing running on your local machine.

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
    