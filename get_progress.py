from datetime import date, datetime, timedelta
from dotenv import load_dotenv

from sqlalchemy.orm import sessionmaker
from database import engine
from models import Folder, Document, DailySnapshot, RevisionEvent

load_dotenv()

def get_progress(session, doc):
    yesterday = datetime.now() - timedelta(days=1)

    if isinstance(doc, Folder):
        # Recursive helper to collect ALL descendant documents
        def collect_descendant_docs(folder):
            # Direct documents
            docs = session.query(Document).filter(
                Document.folder_id == folder.id
            ).all()

            # Direct sub-folders
            subfolders = session.query(Folder).filter(
                Folder.parent_id == folder.id
            ).all()

            for sub in subfolders:
                docs.extend(collect_descendant_docs(sub))

            return docs

        docs = collect_descendant_docs(doc)
        
        snapshots = []
        for d in docs:
            snapshots.extend(
                session.query(DailySnapshot).filter(
                    DailySnapshot.document_id == d.id,
                    DailySnapshot.date >= yesterday
                ).all()
            )
    else:
        # Single document (unchanged)
        snapshots = session.query(DailySnapshot).filter(
            DailySnapshot.document_id == doc.id,
            DailySnapshot.date >= yesterday
        ).all()

    if not snapshots:
        return 0, 0

    # Net added / removed
    added = sum(s.net_added if s.net_added >= 0 else 0 for s in snapshots)
    removed = sum(s.net_added if s.net_added < 0 else 0 for s in snapshots)
    return added, removed

def build_path_with_changes(session):
    # Find all documents with changes and build their paths
    documents = session.query(Document).all()
    folders = session.query(Folder).all()
    
    # Create folder map for path traversal
    folder_map = {folder.id: folder for folder in folders}
    
    # Track documents with changes and their paths
    changed_paths = []
    
    for doc in documents:
        progress = get_progress(session, doc)
        if progress != (0, 0):
            # Build path from root to this document
            path = []
            current_folder_id = doc.folder_id
            
            # Traverse up to root
            while current_folder_id:
                folder = folder_map.get(current_folder_id)
                if folder:
                    path.insert(0, folder)
                    current_folder_id = folder.parent_id
                else:
                    break
            
            # Add the document itself
            path.append(doc)
            changed_paths.append((path, progress))
    
    return changed_paths, folder_map

def print_tree_with_changes(session, changed_paths, folder_map):
    # Print each path from root to changed document
    for path, doc_progress in changed_paths:
        # Calculate aggregated changes for each level
        for i, item in enumerate(path):
            indent = "  " * i
            prefix = "└─ " if i > 0 else ""
            
            if isinstance(item, Folder):
                # Sum all changes in this folder's subtree for changed documents
                folder_progress = get_progress(session, item)
                print(f"{indent}{prefix}📁 {item.name}   ➕ Added: {folder_progress[0]} words | ➖ Removed: {abs(folder_progress[1])} words")
            else:
                # This is a document
                print(f"{indent}{prefix}📄 {item.name}   ➕ Added: {doc_progress[0]} words | ➖ Removed: {abs(doc_progress[1])} words")
        
        print()

def main():
    Session = sessionmaker(bind=engine)
    session = Session()

    # Build paths with changes
    changed_paths, folder_map = build_path_with_changes(session)
    
    # Display in tree format
    if changed_paths:
        print_tree_with_changes(session, changed_paths, folder_map)
    else:
        print("No changes detected.")

if __name__ == "__main__":    
    main()