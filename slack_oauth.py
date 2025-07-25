from fastapi import FastAPI, Request, Depends, HTTPException, Header
import requests
import dotenv
import os
from sqlalchemy.orm import Session
from models import User
from dependencies import get_db, get_current_user

app = FastAPI()

dotenv.load_dotenv()

CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI")
# token=os.getenv("TOKEN")

@app.get("/slack/install")
def slack_install():
    return {
        "url": f"https://slack.com/oauth/v2/authorize"
               f"?client_id={CLIENT_ID}"
               f"&scope=channels:history,groups:history,im:history,channels:read,groups:read,im:read,users:read"
               f"&user_scope=channels:read,groups:read,im:read,mpim:read,channels:history,groups:history,im:history,mpim:history,users:read"
               f"&redirect_uri={REDIRECT_URI}"
    }

@app.get("/slack/oauth/callback")
def slack_oauth_callback(code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    token_url = "https://slack.com/api/oauth.v2.access"
    response = requests.post(token_url, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI
    })

    token_data = response.json()
    
    # Extract user token if present
    user_token = token_data.get("authed_user", {}).get("access_token")

    token = user_token  # Store the token for future use, e.g., in a database or environment variable

    # Store token in DB
    current_user.slack_token = response.text  # Store the full token response as JSON string
    db.commit()
    db.refresh(current_user)

    # Store this somewhere or just return it for now
    return {
        "user_token": user_token,
    }

def get_user_info(access_token, user_id):
    url = "https://slack.com/api/users.info"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"user": user_id}
    res = requests.get(url, headers=headers, params=params)
    return res.json()

def get_channels(access_token):
    url = "https://slack.com/api/conversations.list"
    res = requests.get(url, headers={"Authorization": f"Bearer {access_token}"})
    return res.json()

def get_channel_messages(access_token, channel_id):
    url = f"https://slack.com/api/conversations.history?channel={channel_id}"
    res = requests.get(url, headers={"Authorization": f"Bearer {access_token}"})
    messages_data = res.json()
    
    # Fetch user info for each message
    if messages_data.get("ok"):
        for message in messages_data.get("messages", []):
            if "user" in message:
                user_info = get_user_info(access_token, message["user"])
                if user_info.get("ok"):
                    message["username"] = user_info["user"]["name"]
                    message["real_name"] = user_info["user"]["real_name"]
    
    return messages_data

def get_all_conversations(access_token):
    url = "https://slack.com/api/conversations.list"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "types": "public_channel,private_channel,im,mpim"  # include DMs and private groups
    }
    res = requests.get(url, headers=headers, params=params)
    conversations_data = res.json()
    
    # Add user info for DMs
    if conversations_data.get("ok"):
        for conv in conversations_data.get("channels", []):
            if conv.get("is_im") and "user" in conv:
                user_info = get_user_info(access_token, conv["user"])
                if user_info.get("ok"):
                    conv["username"] = user_info["user"]["name"]
                    conv["real_name"] = user_info["user"]["real_name"]
    
    return conversations_data

# New API endpoints
@app.get("/channels")
async def list_channels(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    import json
    if not current_user.slack_token:
        return {"error": "Not authenticated. Please install and authorize first."}
    token_data = json.loads(current_user.slack_token)
    user_token = token_data.get("authed_user", {}).get("access_token")
    return get_channels(user_token)

@app.get("/channels/{channel_id}/messages")
async def list_messages(channel_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    import json
    if not current_user.slack_token:
        return {"error": "Not authenticated. Please install and authorize first."}
    token_data = json.loads(current_user.slack_token)
    user_token = token_data.get("authed_user", {}).get("access_token")
    return get_channel_messages(user_token, channel_id)

@app.get("/conversations")
async def list_conversations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    import json
    if not current_user.slack_token:
        return {"error": "Not authenticated. Please install and authorize first."}
    token_data = json.loads(current_user.slack_token)
    user_token = token_data.get("authed_user", {}).get("access_token")
    return get_all_conversations(user_token)
