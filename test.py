# Test on a folder with only one docs
# Test how revision got from api
# Conclusion: Google docs doesn't provide word-level change info in revisions.
# Solution: Just pull the entire text and then use the google drive api, compare offline.
from googleapiclient.discovery import build

import google_docs

# Test folder
FOLDER_ID = '1Rx_sUXSJEMvZ0mlb08zJ7epNnYTcdHgW'

def main():
    creds = google_docs.get_credentials()
    service_drive = build('drive', 'v3', credentials=creds)
    service_docs = build('docs', 'v1', credentials=creds, static_discovery=False)
    
    # Get all document in the folder
    query = f"'{FOLDER_ID}' in parents"
    results = service_drive.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    print(items)
    
    # Get revisions for the first document
    if items:
        doc_id = items[0]['id']
        revisions = service_drive.revisions().list(fileId=doc_id).execute().get('revisions', [])
        print(f"Revisions for document {items[0]['name']}:")
        for rev in revisions:
            print(rev)
            # Try to access the revision through docs api
            request = service_docs.documents().get(documentId=doc_id)
            if rev['id']:
                sep = '&' if '?' in request.uri else '?'
                request.uri += f"{sep}revisionId={rev['id']}"
            doc = request.execute()
            
    
if __name__ == "__main__":    
    main()