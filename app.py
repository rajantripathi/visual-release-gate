"""Safe, precomputed Streamlit explorer for the fictional benchmark."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import streamlit as st

from visual_release_gate.pack import load_pack

ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="Visual Release Gate",
    page_icon="◈",
    layout="wide",
)

st.markdown(
    """
    <style>
    :root { --navy:#092a54; --blue:#45a7e8; --coral:#ff6856; --cream:#fff8e8; }
    .stApp { background: #fffdf7; color: #152238; }
    .hero { padding: 1.2rem 0 .5rem 0; border-bottom: 3px solid #092a54; }
    .hero h1 { color:#092a54; margin-bottom:.15rem; }
    .status {
      color:#7a4d00; background:#fff2c7; padding:.7rem 1rem;
      border-left:5px solid #f2b134;
    }
    .verdict { font-size:1.15rem; font-weight:700; color:#092a54; }
    </style>
    <div class="hero">
      <h1>Visual Release Gate</h1>
      <p>A vision model observes. Deterministic policy and people decide what ships.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def _pack():
    return load_pack(ROOT / "sample_pack")


pack = _pack()
labels = pack.label_by_asset_id
counts = Counter(label.primary_verdict for label in pack.labels)

st.markdown(
    """
    <div class="status"><strong>Benchmark preview:</strong> decisions shown here
    are provisional author labels. Independent peer review and the personal-key
    live model run are intentionally required before any performance claim.</div>
    """,
    unsafe_allow_html=True,
)

metric_columns = st.columns(5)
metric_columns[0].metric("Cases", len(pack.briefs))
metric_columns[1].metric("Ship", counts["ship"])
metric_columns[2].metric("Reject", counts["reject"])
metric_columns[3].metric("Human review", counts["human_review"])
metric_columns[4].metric("Unsupported", counts["unsupported"])

st.sidebar.header("Explore cases")
split = st.sidebar.selectbox("Split", ["all", "development", "held_out"])
verdict = st.sidebar.selectbox(
    "Provisional verdict", ["all", "ship", "reject", "human_review", "unsupported"]
)
filtered = [
    brief
    for brief in pack.briefs
    if (split == "all" or brief.split == split)
    and (verdict == "all" or labels[brief.asset_id].primary_verdict == verdict)
]
selected_id = st.sidebar.selectbox(
    "Case", [brief.asset_id for brief in filtered], format_func=lambda value: value
)
brief = pack.brief_by_id[selected_id]
label = labels[selected_id]

left, right = st.columns([1.05, 1], gap="large")
with left:
    st.image(str(brief.resolved_image_path), caption=f"Target: {brief.asset_id}")
with right:
    st.caption(brief.split.replace("_", " ").upper())
    st.markdown(f"### {brief.request}")
    st.markdown(
        f'<p class="verdict">Provisional decision: {label.primary_verdict.upper()}</p>',
        unsafe_allow_html=True,
    )
    st.write(label.rationale)
    if brief.required_copy:
        st.write("**Required copy:**", brief.required_copy)
    if brief.qualitative_attributes:
        st.write("**Qualitative attributes:**", ", ".join(brief.qualitative_attributes))
    if brief.external_requirements:
        st.write("**External evidence required:**")
        for requirement in brief.external_requirements:
            st.write(f"- {requirement.description}")

st.divider()
st.subheader("Why the decision layer is deterministic")
architecture = st.columns(3)
architecture[0].markdown(
    "### 1. Observe\nThe VLM returns typed visual findings and source IDs."
)
architecture[1].markdown(
    "### 2. Validate\nPython rejects unknown citations and unsafe semantics."
)
architecture[2].markdown(
    "### 3. Adjudicate\nSerious issues, ambiguity, and absent authority map "
    "to distinct outcomes."
)

with st.expander("Active policy rules"):
    for rule in pack.rules:
        st.markdown(f"**{rule.rule_id} — {rule.title}**  \n{rule.text}")

with st.expander("Approved visual references"):
    columns = st.columns(len(pack.references))
    for column, reference in zip(columns, pack.references, strict=True):
        column.image(str(reference.resolved_image_path), caption=reference.reference_id)

st.caption(
    "No uploads · no provider calls · no API keys · fictional original data · "
    "v0.1.0 preview"
)
