from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import Base, User
import hashlib
import os
from jose import jwt, JWTError
from datetime import datetime, timedelta
from dependencies import get_db, get_current_user
from db import SessionLocal
from slack_oauth import app as slack_app
from gmail_oauth import app as gmail_app

SECRET_KEY = "your-very-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1 hour

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# Base.metadata.create_all(bind=engine)

app = FastAPI()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic models
class SignupRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

# Utility for password hashing
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# Signup route
@app.post("/signup")
def signup(data: SignupRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if user:
        raise HTTPException(status_code=400, detail="Email already registered")
    new_user = User(email=data.email, password_hash=hash_password(data.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully", "user_id": new_user.id}

# Login route
@app.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or user.password_hash != hash_password(data.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    access_token = create_access_token(data={"user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

# Protected route to get current user info
@app.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email
    }

# Mount other apps
app.mount("/slack", slack_app)
app.mount("/gmail", gmail_app)