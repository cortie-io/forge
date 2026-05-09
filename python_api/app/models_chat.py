"""
채팅/유저 엔터프라이즈 모델 (PostgreSQL)
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    messages = relationship('Message', back_populates='user')
    chatrooms = relationship('ChatRoom', secondary='user_chatroom', back_populates='users')

class ChatRoom(Base):
    __tablename__ = 'chatrooms'
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    users = relationship('User', secondary='user_chatroom', back_populates='chatrooms')
    messages = relationship('Message', back_populates='chatroom')

class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    chatroom_id = Column(Integer, ForeignKey('chatrooms.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship('User', back_populates='messages')
    chatroom = relationship('ChatRoom', back_populates='messages')

class UserChatRoom(Base):
    __tablename__ = 'user_chatroom'
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    chatroom_id = Column(Integer, ForeignKey('chatrooms.id'), primary_key=True)
    joined_at = Column(DateTime, default=datetime.utcnow)
