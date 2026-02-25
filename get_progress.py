from datetime import date, datetime, timedelta
from dotenv import load_dotenv

from sqlalchemy.orm import sessionmaker
from database import engine
from models import Folder, Document, DailySnapshot, RevisionEvent

load_dotenv()

def get_progress(session, doc):
    # Get net change of a document 1 day ago
    # Doc can be a folder or a document
    # If folder, we will sum up all documents in the folder, recursively if needed
    one_day_ago = datetime.now() - timedelta(days=1)
    if isinstance(doc, Folder):
        # If it's a folder, get all documents in the folder
        docs = session.query(Document).filter(Document.folder_id == doc.id).all()
        snapshots = []
        for d in docs:
            snapshots.extend(session.query(DailySnapshot).filter(DailySnapshot.document_id == d.id,
                                                                 DailySnapshot.date >= one_day_ago).all())
    else:
        snapshots = session.query(DailySnapshot).filter(DailySnapshot.document_id == doc.id,
                                                       DailySnapshot.date >= one_day_ago).all()
    if not snapshots:
        return 0, 0
    
    # Return all add and decrease
    return sum(s.net_added if s.net_added >=0 else 0 for s in snapshots), sum(s.net_added if s.net_added < 0 else 0 for s in snapshots)

def get_all_docs(session):
    # Get all documents and folders
    documents = session.query(Document).all()
    folders = session.query(Folder).all()
    return documents + folders

def main():
    Session = sessionmaker(bind=engine)
    session = Session()

    # Get all objects (documents and folders)
    all_docs = get_all_docs(session)
    
    # Get progress for each document
    for doc in all_docs:
        progress = get_progress(session, doc)
        # If there's any change, logging it
        if progress != (0, 0):
            print(f"Document: {doc.name}, Progress: Added {progress[0]} chars, Removed {abs(progress[1])} chars")

if __name__ == "__main__":    
    main()