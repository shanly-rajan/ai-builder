"""Conversational Third Umpire Chatbot for MCC Cricket Laws RAG."""

import streamlit as st
from src.generation.chain import CricketAdjudicationEngine

# Page configuration
st.set_page_config(
    page_title="MCC Cricket Laws Third Umpire",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling: Hide top toolbar status widget & add in-chat cricket spinner
st.markdown(
    """
    <style>
    /* 1. Hide the top-right toolbar runner/stop status widget completely */
    div[data-testid="stStatusWidget"] {
        visibility: hidden !important;
        display: none !important;
    }
    
    /* 2. Style the in-chat spinner with a spinning cricket ball */
    div[data-testid="stSpinner"] > div {
        border: none !important;
    }
    div[data-testid="stSpinner"]::before {
        content: "🏏";
        font-size: 1.4rem;
        display: inline-block;
        animation: spin-cricket 0.8s infinite linear;
        margin-right: 8px;
    }
    
    @keyframes spin-cricket {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    </style>
    """,
    unsafe_allow_html=True
)

USER_AVATAR = "🧢"            # Batting / Field Captain Cap
REPLAY_SCREEN_AVATAR = "📺"   # Third Umpire TV Replay Screen

@st.cache_resource
def get_engine():
    """Instantiate and cache the adjudication engine."""
    return CricketAdjudicationEngine()

engine = get_engine()

# Initialize conversational session state
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "avatar": REPLAY_SCREEN_AVATAR,
            "content": "👋 **Third Umpire Replay Screen Active.** State any match incident, dismissal dispute, or penalty scenario to review against the MCC Laws.",
            "citations": []
        }
    ]

# Sidebar Controls & Quick Scenarios
with st.sidebar:
    st.header("⚙️ TV Umpire Controls")
    top_k = st.slider("Pinecone Retrieval Depth (Top-K)", min_value=1, max_value=8, value=4)
    
    st.markdown("---")
    st.subheader("⚡ Review Presets")
    
    presets = [
        "Non-striker run out before delivery release (Law 38.3)",
        "Ball deflects off pad and hits helmet on turf (Law 28.3)",
        "Batter kicks rolling ball away to save wicket (Law 34.3)",
        "Airborne boundary catch relay (Law 19.5)",
        "Can captain challenge Wide ball using DRS? (Refusal Test)"
    ]
    
    for preset in presets:
        if st.button(preset, use_container_width=True):
            st.session_state.next_prompt = preset

    st.markdown("---")
    if st.button("🗑️ Clear Review Feed", type="secondary", use_container_width=True):
        st.session_state.messages = [st.session_state.messages[0]]
        st.rerun()

# Main Chat View
st.title("🏏 MCC Third Umpire Copilot")
st.caption("Conversational, document-backed adjudicator powered by Pinecone Serverless & GPT-4o")

# Render chat history
for msg in st.session_state.messages:
    avatar_icon = msg.get("avatar", REPLAY_SCREEN_AVATAR if msg["role"] == "assistant" else USER_AVATAR)
    with st.chat_message(msg["role"], avatar=avatar_icon):
        if "⚠️" in msg["content"]:
            st.warning(msg["content"])
        else:
            st.markdown(msg["content"])
            
        if msg.get("citations"):
            with st.expander(f"📚 Grounded Citations ({len(msg['citations'])} Clauses)"):
                for doc in msg["citations"]:
                    law_no = doc.metadata.get("law_number", "N/A")
                    section = doc.metadata.get("section", "Clause")
                    st.markdown(f"**📌 Law {law_no}: {section}**")
                    st.write(doc.page_content.strip())
                    st.divider()

# Handle input from chat bar or quick-scenario buttons
prompt = st.chat_input("Ask about a match scenario, dismissal, or penalty...")
if hasattr(st.session_state, "next_prompt") and st.session_state.next_prompt:
    prompt = st.session_state.next_prompt
    st.session_state.next_prompt = None

if prompt:
    # 1. Append user message
    st.session_state.messages.append({
        "role": "user",
        "avatar": USER_AVATAR,
        "content": prompt,
        "citations": []
    })
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt)

    # 2. Adjudicate via RAG Engine with Replay Screen avatar and in-chat spinner
    with st.chat_message("assistant", avatar=REPLAY_SCREEN_AVATAR):
        with st.spinner("Checking replay angles against MCC Laws..."):
            verdict, docs = engine.adjudicate(prompt, top_k=top_k)
            
            if "⚠️" in verdict:
                st.warning(verdict)
            else:
                st.markdown(verdict)

            if docs:
                with st.expander(f"📚 Grounded Citations ({len(docs)} Clauses)"):
                    for doc in docs:
                        law_no = doc.metadata.get("law_number", "N/A")
                        section = doc.metadata.get("section", "Clause")
                        st.markdown(f"**📌 Law {law_no}: {section}**")
                        st.write(doc.page_content.strip())
                        st.divider()

    # 3. Append assistant response to history
    st.session_state.messages.append({
        "role": "assistant",
        "avatar": REPLAY_SCREEN_AVATAR,
        "content": verdict,
        "citations": docs
    })