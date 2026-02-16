import difflib
import io
import logging
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from sqlalchemy.orm import sessionmaker
from database import engine, get_db
from models import Folder, Document, DailySnapshot, RevisionEvent

# ========================= CONFIG =========================
load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_ID = os.getenv("FOLDER_ID")
SNAPSHOTS_DIR: Path = Path(os.getenv("SNAPSHOTS_DIR", "snapshots"))

# ========================= LOGGING =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


# ========================= HELPERS =========================
def get_credentials():
    """Authenticate with Google and return credentials (reuses token if valid)."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return creds


def get_document_text(service_drive, doc_id: str) -> str:
    """Export Google Doc as clean plain text using Drive API (handles tables, lists, etc.)."""
    try:
        request = service_drive.files().export_media(
            fileId=doc_id, mimeType="text/plain"
        )
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        return fh.read().decode("utf-8")
    except HttpError as e:
        logging.error(f"Failed to export document {doc_id}: {e}")
        return ""
    except Exception as e:
        logging.error(f"Unexpected error exporting document {doc_id}: {e}")
        return ""


def load_previous_text(doc_id: str) -> str:
    """Load previous snapshot or return empty string."""
    path = SNAPSHOTS_DIR / f"{doc_id}.txt"
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            logging.error(f"Failed to read previous text for {doc_id}: {e}")
    return ""


def save_current_text(doc_id: str, text: str):
    """Save current document text as new snapshot."""
    path = SNAPSHOTS_DIR / f"{doc_id}.txt"
    try:
        path.write_text(text, encoding="utf-8")
    except Exception as e:
        logging.error(f"Failed to save current text for {doc_id}: {e}")


def compute_diff(prev_text: str, curr_text: str) -> tuple[int, int]:
    """
    Word-level diff using SequenceMatcher.
    Returns (words_added, words_deleted).
    On first run (no prev_text) treats entire current text as added.
    """
    prev_words = prev_text.split() if prev_text else []
    curr_words = curr_text.split()

    if not prev_words:
        return len(curr_words), 0

    matcher = difflib.SequenceMatcher(None, prev_words, curr_words)
    added = deleted = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            added += j2 - j1
        elif tag == "delete":
            deleted += i2 - i1
        elif tag == "replace":
            deleted += i2 - i1
            added += j2 - j1

    return added, deleted


def list_drive_files(service_drive, folder_id: str):
    """List all non-trashed files/folders with full pagination."""
    items = []
    page_token = None
    while True:
        try:
            results = service_drive.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token,
            ).execute()
            items.extend(results.get("files", []))
            page_token = results.get("nextPageToken")
            if not page_token:
                break
        except HttpError as e:
            logging.error(f"Failed to list files in folder {folder_id}: {e}")
            break
        except Exception as e:
            logging.error(f"Unexpected error listing folder {folder_id}: {e}")
            break
    return items


# ========================= MAIN PROCESSING =========================
def process_folder(
    service_drive, db, folder_id: str, parent_folder: Folder | None = None, indent: str = ""
) -> int:
    """Recursively process a Drive folder, track documents, and compute changes."""
    # Ensure folder exists in DB (and update name if changed)
    folder = db.get(Folder, folder_id)
    if not folder:
        if folder_id == FOLDER_ID:
            folder_name = "Root"
        else:
            try:
                meta = service_drive.files().get(fileId=folder_id, fields="name").execute()
                folder_name = meta["name"]
            except Exception:
                folder_name = f"Folder_{folder_id[:8]}"
        folder = Folder(
            id=folder_id,
            name=folder_name,
            parent_id=parent_folder.id if parent_folder else None,
        )
        db.add(folder)
    else:
        # Update name on rename (skip root)
        if folder_id != FOLDER_ID:
            try:
                meta = service_drive.files().get(fileId=folder_id, fields="name").execute()
                if meta["name"] != folder.name:
                    folder.name = meta["name"]
            except Exception:
                pass

    total_words = 0
    items = list_drive_files(service_drive, folder_id)

    for item in items:
        mime = item["mimeType"]

        if mime == "application/vnd.google-apps.document":
            # Ensure document exists in DB (update name/folder if needed)
            doc = db.get(Document, item["id"])
            if not doc:
                doc = Document(
                    id=item["id"],
                    name=item["name"],
                    folder_id=folder_id,
                )
                db.add(doc)
            else:
                if item["name"] != doc.name:
                    doc.name = item["name"]
                doc.folder_id = folder_id  # handle moves within monitored tree

            curr_text = get_document_text(service_drive, item["id"])
            curr_words = len(curr_text.split())

            prev_text = load_previous_text(item["id"])
            added, deleted = compute_diff(prev_text, curr_text)
            net = added - deleted

            # Always record revision event (including initial sync)
            event = RevisionEvent(
                document_id=doc.id,
                timestamp=date.today(),
                words_added=added,
                words_deleted=deleted,
                net_change=net,
            )
            db.add(event)

            # Daily snapshot (accumulate net change if multiple runs same day)
            today = date.today()
            snapshot = (
                db.query(DailySnapshot)
                .filter_by(document_id=doc.id, date=today)
                .first()
            )
            if not snapshot:
                snapshot = DailySnapshot(
                    document_id=doc.id,
                    date=today,
                    total_words=curr_words,
                    net_added=net,
                )
                db.add(snapshot)
            else:
                snapshot.net_added += net
                snapshot.total_words = curr_words

            doc.total_words = curr_words
            save_current_text(item["id"], curr_text)

            total_words += curr_words
            logging.info(f"{indent}Document: {item['name']} - Words: {curr_words} (Δ {net:+})")

        elif mime == "application/vnd.google-apps.folder":
            logging.info(f"{indent}Folder: {item['name']}")
            sub_total = process_folder(
                service_drive, db, item["id"], parent_folder=folder, indent=indent + "  "
            )
            total_words += sub_total

    return total_words


# ========================= ENTRY POINT =========================
def main():
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    creds = get_credentials()
    service_drive = build("drive", "v3", credentials=creds)

    # Use direct session for clean transaction control (better than next(get_db()) hack)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        logging.info("Starting Google Drive word tracking...")
        total_words = process_folder(service_drive, db, FOLDER_ID)
        db.commit()
        logging.info(f"✅ Completed successfully. Total words across folder: {total_words}")
    except Exception as e:
        db.rollback()
        logging.error(f"❌ Processing failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()