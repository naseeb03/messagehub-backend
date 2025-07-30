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
    current_user.gmail_refresh_token = token_data.get("refresh_token")
    db.commit()
    db.refresh(current_user)
    
    return {
        "message": "Gmail connected successfully!",
        "access_token": token_data.get("access_token")
    }

def refresh_gmail_token(refresh_token):
    """Refresh Gmail access token using refresh token"""
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    response = requests.post(token_url, data=data)
    return response.json()

def get_gmail_service_with_refresh(access_token, refresh_token, db, current_user):
    """Get Gmail service with automatic token refresh"""
    try:
        # First try with current access token
        creds = Credentials(
            token=access_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=SCOPES
        )
        service = build('gmail', 'v1', credentials=creds)
        
        # Test the service with a simple call
        service.users().getProfile(userId='me').execute()
        return service
        
    except Exception as e:
        # If access token is expired, refresh it
        print(f"Token expired, refreshing: {e}")
        try:
            new_token_data = refresh_gmail_token(refresh_token)
            new_access_token = new_token_data.get("access_token")
            
            if new_access_token:
                # Update the token in database
                current_user.gmail_token = new_access_token
                db.commit()
                
                # Create new credentials with fresh token
                creds = Credentials(
                    token=new_access_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=GOOGLE_CLIENT_ID,
                    client_secret=GOOGLE_CLIENT_SECRET,
                    scopes=SCOPES
                )
                service = build('gmail', 'v1', credentials=creds)
                return service
            else:
                raise Exception("Failed to refresh token")
                
        except Exception as refresh_error:
            print(f"Failed to refresh token: {refresh_error}")
            raise Exception("Token refresh failed")

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

def get_emails_with_refresh(access_token, refresh_token, db, current_user, max_results=10):
    """Get emails with automatic token refresh"""
    service = get_gmail_service_with_refresh(access_token, refresh_token, db, current_user)
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

@app.get("/emails")
async def list_emails(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.gmail_token or not current_user.gmail_refresh_token:
        return {"error": "Not authenticated. Please install and authorize first."}
    
    try:
        emails = get_emails_with_refresh(
            current_user.gmail_token, 
            current_user.gmail_refresh_token, 
            db, 
            current_user
        )
        return {"emails": emails}
    except Exception as e:
        return {"error": f"Failed to fetch emails: {str(e)}"}