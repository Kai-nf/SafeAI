import streamlit as st
from supabase import create_client
import plotly.graph_objects as go
from sklearn.decomposition import PCA
import json

st.set_page_config(page_title="LSTT Security Dashboard", page_icon="🛡️")
st.title("🛡️ LSTT Security Dashboard")

supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

session_id = st.text_input("Session ID to inspect", value=st.session_state.get("session_id", ""))

if st.button("Refresh") and session_id:
    result = supabase.table("conversations") \
        .select("*") \
        .eq("session_id", session_id) \
        .order("timestamp") \
        .execute()

    rows = [r for r in result.data if r.get("embedding_vector")]

    if len(rows) < 2:
        st.info("Not enough embedded turns yet. Wait a few seconds after chatting and refresh again.")
    else:
        vectors = [json.loads(r["embedding_vector"]) if isinstance(r["embedding_vector"], str)
                   else r["embedding_vector"] for r in rows]
        pca = PCA(n_components=2)
        coords = pca.fit_transform(vectors)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=coords[:, 0], y=coords[:, 1],
            mode="lines+markers+text",
            text=[f"Turn {i+1}" for i in range(len(coords))],
            textposition="top center",
            name="Conversation path"
        ))
        flagged = any(r.get("flagged") for r in rows)
        if flagged:
            st.error("⚠️ This session was flagged as high risk by the LSTT plugin.")
        st.plotly_chart(fig, use_container_width=True)

st.subheader("Images shared in this session")
image_rows = [r for r in result.data if r.get("image_url")]
if image_rows:
    cols = st.columns(min(len(image_rows), 4))
    for i, row in enumerate(image_rows):
        with cols[i % 4]:
            st.image(row["image_url"], caption=row.get("content_type", ""))
else:
    st.caption("No images in this session yet.")