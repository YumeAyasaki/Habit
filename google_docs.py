
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os.path
import io

SCOPES = ['https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/documents.readonly']

def get_credentials():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def get_word_count(service_docs, doc_id):
    doc = service_docs.documents().get(documentId=doc_id).execute()
    content = doc.get('body').get('content')
    text = ''
    for elem in content:
        if 'paragraph' in elem:
            for item in elem['paragraph']['elements']:
                if 'textRun' in item:
                    text += item['textRun']['content']
    return len(text.split())  # Simple word count

def main(folder_id):
    creds = get_credentials()
    service_drive = build('drive', 'v3', credentials=creds)
    service_docs = build('docs', 'v1', credentials=creds)
    
    # List Google Docs in folder
    query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.document'"
    results = service_drive.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    
    total_words = 0
    # Recursively get word counts and show for every document even in subfolders
    # Show also the tree structure
    def process_folder(folder_id, indent=''):
        nonlocal total_words
        query = f"'{folder_id}' in parents"
        results = service_drive.files().list(q=query, fields="files(id, name, mimeType)").execute()
        items = results.get('files', [])
        
        for item in items:
            if item['mimeType'] == 'application/vnd.google-apps.document':
                word_count = get_word_count(service_docs, item['id'])
                total_words += word_count
                print(f"{indent}Document: {item['name']} - Words: {word_count}")
            elif item['mimeType'] == 'application/vnd.google-apps.folder':
                print(f"{indent}Folder: {item['name']}")
                process_folder(item['id'], indent + '  ')

    process_folder(folder_id)
    
    print(f"Total words across folder: {total_words}")
    # Store in Postgres for tracking over time

if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()
    folder_id = os.getenv('FOLDER_ID')
    main(folder_id)