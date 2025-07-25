from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    gmail_token = Column(Text, nullable=True)
    outlook_token = Column(Text, nullable=True)
    slack_token = Column(Text, nullable=True)
    jira_token = Column(Text, nullable=True)

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}')>"
