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

@app.get("/install")
def gmail_install(current_user: User = Depends(get_current_user)):
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": str(current_user.id)
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return {"url": url}

@app.get("/oauth/callback")
def gmail_oauth_callback(code: str, state: str, db: Session = Depends(get_db)):
    # Find user by ID from state parameter
    try:
        user_id = int(state)
        current_user = db.query(User).filter(User.id == user_id).first()
        if not current_user:
            raise HTTPException(status_code=404, detail="User not found")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    
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
    
    # Store only the access token in DB
    current_user.gmail_token = token_data.get("access_token")
    db.commit()
    db.refresh(current_user)
    
    return {
        "message": "Gmail connected successfully!",
        "access_token": token_data.get("access_token")
    }

def get_gmail_service(access_token):
    creds = Credentials(
        token=access_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES
    )
    service = build('gmail', 'v1', credentials=creds)
    return service

def get_emails(access_token, max_results=10):
    service = get_gmail_service(access_token)
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
    emails = get_emails(current_user.gmail_token)
    return {"emails": emails}