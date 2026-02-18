import streamlit as st
import pandas as pd
from datetime import date, timedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func
from dotenv import load_dotenv
import os

# Import your DB setup (adjust paths if needed)
from database import engine
from models import Document, DailySnapshot, Folder

load_dotenv()
st.set_page_config(layout="wide")

# DB Session
SessionLocal = sessionmaker(bind=engine)

# Helper to build full path for a document
def get_doc_path(db, doc):
    path = doc.name
    folder = db.get(Folder, doc.folder_id)
    while folder:
        path = f"{folder.name}/{path}"
        folder = db.get(Folder, folder.parent_id)
    return path

# Cache queries for performance
@st.cache_data(ttl=300)  # Refresh every 5 min
def get_db_data(selected_date, selected_doc_id):
    with SessionLocal() as db:
        doc_filter = Document.id == selected_doc_id if selected_doc_id != "All" else True

        # Words Today: sum(net_added) on selected date
        words_today = db.query(func.sum(DailySnapshot.net_added)).filter(
            DailySnapshot.date == selected_date,
            DailySnapshot.document_id.in_(db.query(Document.id).filter(doc_filter))
        ).scalar() or 0

        # Words This Week: sum(net_added) over week (Mon-Sun)
        week_start = selected_date - timedelta(days=selected_date.weekday())
        words_week = db.query(func.sum(DailySnapshot.net_added)).filter(
            DailySnapshot.date >= week_start,
            DailySnapshot.date <= selected_date,
            DailySnapshot.document_id.in_(db.query(Document.id).filter(doc_filter))
        ).scalar() or 0

        # Total Words: sum(current total_words from Documents)
        total_words = db.query(func.sum(Document.total_words)).filter(doc_filter).scalar() or 0

        # Trend data: sum(net_added) per day, last 30 days
        trend_start = selected_date - timedelta(days=30)
        trend_query = db.query(DailySnapshot.date, func.sum(DailySnapshot.net_added)).filter(
            DailySnapshot.date >= trend_start,
            DailySnapshot.date <= selected_date,
            DailySnapshot.document_id.in_(db.query(Document.id).filter(doc_filter))
        ).group_by(DailySnapshot.date).order_by(DailySnapshot.date)
        trend_df = pd.DataFrame(trend_query.all(), columns=["date", "words"])
        trend_df = trend_df.set_index("date").reindex(pd.date_range(trend_start, selected_date)).fillna(0)

        # Doc breakdown: current totals, with paths
        doc_query = db.query(Document.id, Document.name, Document.total_words, Document.folder_id).filter(doc_filter)
        doc_data = []
        for d_id, name, words, f_id in doc_query.all():
            path = get_doc_path(db, Document(id=d_id, name=name, folder_id=f_id))
            doc_data.append({"document": path, "words": words})
        doc_df = pd.DataFrame(doc_data)

        # Streak: consecutive days back from selected_date with sum(net_added) >0 per day (no gaps)
        snapshots = db.query(DailySnapshot.date, func.sum(DailySnapshot.net_added).label('daily_added')).filter(
            DailySnapshot.date <= selected_date,
            DailySnapshot.document_id.in_(db.query(Document.id).filter(doc_filter))
        ).group_by(DailySnapshot.date).order_by(DailySnapshot.date.desc()).all()
        streak = 0
        expected_date = selected_date
        for d, added in snapshots:
            if d == expected_date:
                if added > 0:
                    streak += 1
                    expected_date -= timedelta(days=1)
                else:
                    break
            elif d < expected_date:
                break  # Gap in dates → stop

        # Tree structure: recursive build
        def build_tree(folder, indent=0):
            tree = [{"name": folder.name, "type": "folder", "words": 0, "indent": indent}]
            # Subfolders
            for sub in db.query(Folder).filter(Folder.parent_id == folder.id).all():
                sub_tree = build_tree(sub, indent + 1)
                tree[0]["words"] += sub_tree[0]["words"]
                tree.extend(sub_tree)
            # Docs
            docs = db.query(Document).filter(Document.folder_id == folder.id).all()
            for doc in docs:
                words = doc.total_words or 0
                tree[0]["words"] += words
                tree.append({"name": doc.name, "type": "doc", "words": words, "indent": indent + 1})
            return tree

        tree_data = []
        root_folders = db.query(Folder).filter(Folder.parent_id.is_(None)).all()
        for root in root_folders:
            tree_data.extend(build_tree(root))

        return {
            "words_today": words_today,
            "words_week": words_week,
            "total_words": total_words,
            "trend_df": trend_df,
            "doc_df": doc_df,
            "streak": streak,
            "tree_data": tree_data,
            "has_data": total_words > 0
        }

# --------------------
# SIDEBAR
# --------------------
st.sidebar.title("Filters")

selected_date = st.sidebar.date_input(
    "Select date",
    value=date.today()
)

# Dynamic doc options with full paths
with SessionLocal() as db:
    docs = db.query(Document).all()
    doc_options = {"All": "All"}
    for doc in docs:
        path = get_doc_path(db, doc)
        doc_options[path] = doc.id

selected_path = st.sidebar.selectbox(
    "Select document",
    options=list(doc_options.keys())
)
selected_doc_id = doc_options[selected_path]

if st.sidebar.button("Run Sync Now"):
    os.system("python google_docs.py")  # Assumes google_docs.py in same dir; adjust if needed
    st.sidebar.success("Sync triggered!")

# Fetch data
data = get_db_data(selected_date, selected_doc_id)

# --------------------
# MAIN HEADER
# --------------------
st.title("📖 Writing Habit Tracker")

if not data["has_data"]:
    st.info("No data yet — run the sync script to populate!")

# --------------------
# TOP METRICS
# --------------------
col1, col2, col3, col4 = st.columns(4)

col1.metric("Words Today", data["words_today"])
col2.metric("This Week", data["words_week"])
col3.metric("Total Words", data["total_words"])
col4.metric("Current Streak", f"{data['streak']} days")

st.divider()

# --------------------
# TREND CHART
# --------------------
st.subheader("📈 Writing Trend (Last 30 Days)")
st.line_chart(data["trend_df"])

st.divider()

# --------------------
# DOCUMENT BREAKDOWN
# --------------------
st.subheader("📂 Document Breakdown")
st.bar_chart(data["doc_df"].set_index("document"))

st.divider()

# --------------------
# FOLDER TREE VIEW
# --------------------
st.subheader("🌳 Folder Structure")
if data["tree_data"]:
    for item in data["tree_data"]:
        indent_str = "  " * item["indent"]
        st.write(f"{indent_str}- {item['name']} ({item['type']}): {item['words']} words")
else:
    st.info("No folders/docs found.")

# --------------------
# RAW TABLE (OPTIONAL)
# --------------------
with st.expander("Show Raw Data"):
    st.dataframe(data["trend_df"].reset_index())