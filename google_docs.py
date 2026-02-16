import difflib
import io
import logging
import os
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from sqlalchemy.orm import sessionmaker
from database import engine
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
    try:
        request = service_drive.files().export_media(fileId=doc_id, mimeType="text/plain")
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        return fh.read().decode("utf-8")
    except Exception as e:
        logging.error(f"Failed to export document {doc_id}: {e}")
        return ""


def load_previous_text(doc_id: str) -> str:
    path = SNAPSHOTS_DIR / f"{doc_id}.txt"
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            logging.error(f"Failed to read previous text for {doc_id}: {e}")
    return ""


def save_current_text(doc_id: str, text: str):
    path = SNAPSHOTS_DIR / f"{doc_id}.txt"
    try:
        path.write_text(text, encoding="utf-8")
    except Exception as e:
        logging.error(f"Failed to save current text for {doc_id}: {e}")


def compute_diff(prev_text: str, curr_text: str) -> tuple[int, int]:
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
        except Exception as e:
            logging.error(f"Failed to list files in folder {folder_id}: {e}")
            break
    return items


def get_latest_revision_id(service_drive, doc_id: str) -> str | None:
    """Cheap call – only returns the newest revision ID."""
    try:
        response = service_drive.revisions().list(
            fileId=doc_id,
            pageSize=1,
            fields="revisions(id)",
        ).execute()
        revisions = response.get("revisions", [])
        return revisions[0]["id"] if revisions else None
    except HttpError as e:
        if e.resp.status in (403, 404):
            logging.warning(f"Revisions not accessible for doc {doc_id} (permission/trashed?)")
        else:
            logging.error(f"Failed to fetch revision for {doc_id}: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error fetching revision {doc_id}: {e}")
        return None


# ========================= MAIN PROCESSING =========================
def process_folder(
    service_drive, db, folder_id: str, parent_folder: Folder | None = None, indent: str = ""
) -> int:
    # Folder bookkeeping
    folder = db.get(Folder, folder_id)
    if not folder:
        folder_name = "Root" if folder_id == FOLDER_ID else service_drive.files().get(
            fileId=folder_id, fields="name"
        ).execute()["name"]
        folder = Folder(
            id=folder_id,
            name=folder_name,
            parent_id=parent_folder.id if parent_folder else None,
        )
        db.add(folder)
    else:
        if folder_id != FOLDER_ID:
            try:
                new_name = service_drive.files().get(fileId=folder_id, fields="name").execute()["name"]
                if new_name != folder.name:
                    folder.name = new_name
            except Exception:
                pass

    total_words = 0
    items = list_drive_files(service_drive, folder_id)

    for item in items:
        if item["mimeType"] == "application/vnd.google-apps.document":
            doc = db.get(Document, item["id"])
            if not doc:
                doc = Document(id=item["id"], name=item["name"], folder_id=folder_id)
                db.add(doc)
            else:
                if item["name"] != doc.name:
                    doc.name = item["name"]
                doc.folder_id = folder_id

            # === REVISION OPTIMIZATION ===
            current_rev_id = get_latest_revision_id(service_drive, item["id"])

            if doc.last_revision_id and current_rev_id == doc.last_revision_id:
                # Unchanged – ultra-fast path
                curr_words = doc.total_words or 0
                logging.info(f"{indent}Document: {item['name']} - Unchanged (rev {current_rev_id})")

                # Ensure today’s snapshot exists
                today = date.today()
                snapshot = db.query(DailySnapshot).filter_by(document_id=doc.id, date=today).first()
                if not snapshot:
                    snapshot = DailySnapshot(
                        document_id=doc.id,
                        date=today,
                        total_words=curr_words,
                        net_added=0,
                    )
                    db.add(snapshot)

                doc.last_synced = datetime.now()
                total_words += curr_words
                continue

            # === CHANGED OR FIRST SYNC – full processing ===
            curr_text = get_document_text(service_drive, item["id"])
            curr_words = len(curr_text.split())

            prev_text = load_previous_text(item["id"])
            added, deleted = compute_diff(prev_text, curr_text)
            net = added - deleted

            # Record the change with revision ID
            event = RevisionEvent(
                document_id=doc.id,
                revision_id=current_rev_id,          # ← utilizing your field
                timestamp=datetime.now(),
                words_added=added,
                words_deleted=deleted,
                net_change=net,
            )
            db.add(event)

            # Daily snapshot
            today = date.today()
            snapshot = db.query(DailySnapshot).filter_by(document_id=doc.id, date=today).first()
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

            # Update revision tracking
            doc.last_revision_id = current_rev_id
            doc.last_synced = datetime.now()

            total_words += curr_words
            logging.info(f"{indent}Document: {item['name']} - Words: {curr_words} (Δ {net:+}, new rev {current_rev_id})")

        elif item["mimeType"] == "application/vnd.google-apps.folder":
            logging.info(f"{indent}Folder: {item['name']}")
            sub_total = process_folder(service_drive, db, item["id"], parent_folder=folder, indent=indent + "  ")
            total_words += sub_total

    return total_words


# ========================= ENTRY POINT =========================
def main():
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    creds = get_credentials()
    service_drive = build("drive", "v3", credentials=creds)

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        logging.info("Starting optimized Google Drive word tracking...")
        total_words = process_folder(service_drive, db, FOLDER_ID)
        db.commit()
        logging.info(f"✅ Completed. Total words: {total_words}")
    except Exception as e:
        db.rollback()
        logging.error(f"❌ Failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()