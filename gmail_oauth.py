from fastapi import FastAPI, Request, Depends, HTTPException, Header
import dotenv
import os
import requests
from urllib.parse import urlencode
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session
from models import User
from dependencies import get_db, get_current_user

app = FastAPI()

dotenv.load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "email",
    "profile"
]

token = None  # Store the token for demonstration; in production, use a DB or session

@app.get("/gmail/install")
def gmail_install():
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent"
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return {"url": url}

@app.get("/gmail/oauth/callback")
def gmail_oauth_callback(code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    response = requests.post(token_url, data=data)
    token_data = response.json()
    global token
    token = token_data  # Store for demonstration
    # Store token in DB
    current_user.gmail_token = response.text  # Store the full token response as JSON string
    db.commit()
    db.refresh(current_user)
    return {"token": token_data}

def get_gmail_service(token_data):
    creds = Credentials(
        token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES
    )
    service = build('gmail', 'v1', credentials=creds)
    return service

def get_emails(token_data, max_results=10):
    service = get_gmail_service(token_data)
    results = service.users().messages().list(
    userId='me',
    maxResults=max_results,
    labelIds=['INBOX', 'CATEGORY_PERSONAL']
).execute()
    messages = results.get('messages', [])
    emails = []
    for msg in messages:
        msg_detail = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
        emails.append({
            'id': msg['id'],
            'snippet': msg_detail.get('snippet'),
            'headers': msg_detail.get('payload', {}).get('headers', [])
        })
    return emails

@app.get("/gmail/emails")
async def list_emails(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.gmail_token:
        return {"error": "Not authenticated. Please install and authorize first."}
    import json
    token_data = json.loads(current_user.gmail_token)
    emails = get_emails(token_data)
    return {"emails": emails}