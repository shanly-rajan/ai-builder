"""Streamlit Web UI for the MCC Cricket Laws & Match Scenarios Adjudicator."""

import streamlit as st
from src.generation.chain import CricketAdjudicationEngine

# Page configuration
st.set_page_config(
    page_title="MCC Cricket Laws Adjudicator",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="expanded"
)

@st.cache_resource
def get_adjudication_engine():
    """Cache engine instantiation across Streamlit reruns."""
    return CricketAdjudicationEngine()

engine = get_adjudication_engine()

# Sidebar: Controls and presets
with st.sidebar:
    st.header("⚙️ Adjudication Settings")
    top_k = st.slider("Retrieved Clauses (Top-K)", min_value=1, max_value=8, value=4)
    
    st.markdown("---")
    st.subheader("📋 Preset Match Scenarios")
    presets = {
        "Custom Scenario": "",
        "Non-Striker Run Out (Law 38.3)": "Bowler enters delivery stride, sees non-striker backing up too far, and breaks the stumps before releasing the ball. Is it Out?",
        "Ball Hits Helmet on Ground (Law 28.3)": "A deflected ball off the batter pad strikes the fielder helmet lying on the ground behind the keeper. What is the penalty and ball status?",
        "Protecting Wicket with Boot (Law 34.3)": "Batter blocks the ball, it rolls back toward their stumps, and the batter kicks the ball away with their boot to save their wicket. Are they Out?",
        "Airborne Boundary Catch (Law 19.5)": "Fielder catches ball over boundary, tosses it into the air while landing beyond the rope, then jumps back inside to catch it. Is it a legal catch?",
        "Refusal Test (DRS Rule)": "Can the fielding captain challenge a wide ball call using DRS under standard MCC Laws?"
    }
    
    selected_preset = st.selectbox("Choose a scenario:", list(presets.keys()))

# Main Display
st.title("🏏 MCC Cricket Laws Adjudication Engine")
st.caption("Grounded Third Umpire Assistant powered by Pinecone Serverless and GPT-4o")

preset_text = presets[selected_preset]
scenario_input = st.text_area(
    "Enter Match Scenario / Incident Description:",
    value=preset_text,
    placeholder="Describe the match situation...",
    height=120
)

col_btn, _ = st.columns([1, 4])
with col_btn:
    adjudicate_btn = st.button("⚖️ Adjudicate Scenario", type="primary", use_container_width=True)

if adjudicate_btn:
    if not scenario_input.strip():
        st.warning("⚠️ Please provide a match scenario to adjudicate.")
    else:
        with st.spinner("Retrieving grounded clauses from Pinecone and adjudicating..."):
            verdict, retrieved_docs = engine.adjudicate(scenario_input, top_k=top_k)

        col_verdict, col_citations = st.columns([3, 2], gap="medium")

        with col_verdict:
            st.subheader("📋 Official Adjudication")
            # Using a native container ensures full contrast support in dark and light mode
            with st.container(border=True):
                st.markdown(verdict)

        with col_citations:
            st.subheader(f"📚 Grounded Context ({len(retrieved_docs)} Clauses)")
            if not retrieved_docs:
                st.info("No relevant law clauses retrieved.")
            else:
                for i, doc in enumerate(retrieved_docs, 1):
                    law_no = doc.metadata.get("law_number", "N/A")
                    section = doc.metadata.get("section", f"Clause {i}")
                    law_title = doc.metadata.get("law_title", "")
                    
                    with st.expander(f"📌 Law {law_no}: {section}"):
                        if law_title:
                            st.caption(f"**Category/Title:** {law_title}")
                        st.markdown(doc.page_content.strip())