import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import ServerError, APIError
from supabase import create_client
import uuid
import requests
from PIL import Image
import io

st.set_page_config(page_title="Mock Gemini Chat", page_icon="💬")

# --- Connect to Supabase and Gemini using the secrets file ---
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

TEXT_MODEL = "gemini-3.5-flash"
IMAGE_GEN_MODEL = "gemini-2.5-flash-image"  # "Nano Banana" — has a free tier
BUCKET = "conversation-images"

# --- Give this browser tab a session ID that persists while it's open ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []


def upload_image_to_storage(pil_image: Image.Image, session_id: str) -> str:
    """Uploads a PIL image to Supabase Storage and returns its public URL."""
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    buf.seek(0)
    filename = f"{session_id}/{uuid.uuid4()}.png"
    supabase.storage.from_(BUCKET).upload(
        filename, buf.read(), {"content-type": "image/png"}
    )
    return supabase.storage.from_(BUCKET).get_public_url(filename)


st.title("💬 Mock Gemini Chatbot")
st.caption(f"Session ID: {st.session_state.session_id}")

# --- Show past messages in this session ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("image") is not None:
            st.image(msg["image"])
        if msg.get("content"):
            st.write(msg["content"])

# --- Optional image attachment + mode toggle ---
uploaded_file = st.file_uploader("Attach an image (optional)", type=["png", "jpg", "jpeg"])
generate_image_mode = st.checkbox("Generate an image instead of replying with text")

# --- Handle new input ---
prompt = st.chat_input("Type a message...")
if prompt:
    pil_image = Image.open(uploaded_file) if uploaded_file else None

    # Show and store the user's message
    st.session_state.messages.append({"role": "user", "content": prompt, "image": pil_image})
    with st.chat_message("user"):
        if pil_image is not None:
            st.image(pil_image)
        st.write(prompt)

    # Save the user's turn to Supabase, uploading the image first if present
    if pil_image is not None:
        image_url = upload_image_to_storage(pil_image, st.session_state.session_id)
        supabase.table("conversations").insert({
            "session_id": st.session_state.session_id,
            "role": "user",
            "content": prompt,
            "content_type": "image_input",
            "image_url": image_url
        }).execute()
    else:
        supabase.table("conversations").insert({
            "session_id": st.session_state.session_id,
            "role": "user",
            "content": prompt,
            "content_type": "text"
        }).execute()

    # --- SYNCHRONOUS LSTT SAFETY GATE ---
    try:
        plugin_response = requests.post(
            st.secrets["N8N_WEBHOOK_URL"],
            json={"session_id": st.session_state.session_id},
            headers={"ngrok-skip-browser-warning": "true"},
            timeout=8  # Synchronous wait for LSTT verdict
        )
        decision = plugin_response.json()
    except Exception:
        decision = {"flagged": False}  # Fail-open if unreachable

    with st.chat_message("model"):
        if decision.get("flagged"):
            # --- Blocked Branch ---
            block_msg = "⚠️ This request was flagged by the LSTT safety plugin and was not sent to the model."
            st.error(block_msg)
            
            st.session_state.messages.append({"role": "model", "content": block_msg, "image": None})
            
            supabase.table("conversations").insert({
                "session_id": st.session_state.session_id,
                "role": "model",
                "content": block_msg,
                "content_type": "text"
            }).execute()
        else:
            # --- Allowed Branch ---
            if generate_image_mode:
                # --- Image generation ---
                response = client.models.generate_content(
                    model=IMAGE_GEN_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_modalities=["IMAGE"])
                )
                reply_image = None
                for part in response.parts:
                    if part.inline_data:
                        reply_image = part.as_image()

                if reply_image is not None:
                    st.image(reply_image)
                    image_url = upload_image_to_storage(reply_image, st.session_state.session_id)
                    st.session_state.messages.append({"role": "model", "content": None, "image": reply_image})
                    supabase.table("conversations").insert({
                        "session_id": st.session_state.session_id,
                        "role": "model",
                        "content": prompt,
                        "content_type": "image_output",
                        "image_url": image_url
                    }).execute()
            else:
                # --- Text reply, optionally reasoning over an attached image ---
                contents = [prompt, pil_image] if pil_image is not None else [prompt]

                try:
                    response = client.models.generate_content(model=TEXT_MODEL, contents=contents)
                    reply = response.text
                except (ServerError, APIError):
                    reply = "⚠️ The AI service is currently experiencing high load or a temporary outage. Please try sending your message again."

                st.session_state.messages.append({"role": "model", "content": reply, "image": None})
                st.write(reply)

                # Save model reply to Supabase
                supabase.table("conversations").insert({
                    "session_id": st.session_state.session_id,
                    "role": "model",
                    "content": reply,
                    "content_type": "text"
                }).execute()