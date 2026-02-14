import streamlit as st
import pandas as pd
from datetime import date

st.set_page_config(layout="wide")

# --------------------
# SIDEBAR
# --------------------
st.sidebar.title("Filters")

selected_date = st.sidebar.date_input(
    "Select date",
    value=date.today()
)

selected_doc = st.sidebar.selectbox(
    "Select document",
    options=["All", "Doc 1", "Doc 2"]
)

# --------------------
# MAIN HEADER
# --------------------
st.title("📖 Writing Habit Tracker")

# --------------------
# TOP METRICS
# --------------------
col1, col2, col3 = st.columns(3)

col1.metric("Words Today", 1450)
col2.metric("This Week", 7200)
col3.metric("Total Words", 85420)

st.divider()

# --------------------
# TREND CHART
# --------------------
st.subheader("📈 Writing Trend")

dummy_data = pd.DataFrame({
    "date": pd.date_range("2026-01-01", periods=10),
    "words": [500, 700, 0, 1200, 900, 400, 1000, 1100, 0, 1300]
})

st.line_chart(dummy_data.set_index("date"))

st.divider()

# --------------------
# DOCUMENT BREAKDOWN
# --------------------
st.subheader("📂 Document Breakdown")

doc_data = pd.DataFrame({
    "document": ["Doc 1", "Doc 2", "Doc 3"],
    "words": [30000, 25000, 30420]
})

st.bar_chart(doc_data.set_index("document"))

# --------------------
# RAW TABLE (OPTIONAL)
# --------------------
with st.expander("Show Raw Data"):
    st.dataframe(dummy_data)
