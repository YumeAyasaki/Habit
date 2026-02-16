from sqlalchemy import Column, Integer, String, Date, ForeignKey, DateTime, Float, Text, func
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Folder(Base):
    __tablename__ = "folders"
    id = Column(String, primary_key=True)          # Google Drive folder ID
    name = Column(String, nullable=False)
    parent_id = Column(String, ForeignKey("folders.id"), nullable=True)  # Tree structure
    last_synced = Column(DateTime, default=func.now())

    children = relationship("Folder", backref="parent", remote_side=[id])
    documents = relationship("Document", back_populates="folder")

class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True)          # Google Doc ID
    name = Column(String, nullable=False)
    folder_id = Column(String, ForeignKey("folders.id"))
    # subject = Column(String, nullable=True)        # e.g., "Math", "Novel" – manual or inferred
    total_words = Column(Integer, default=0)
    last_synced = Column(DateTime, default=func.now())
    last_revision_id = Column(String, nullable=True)  # To track changes since last sync

    folder = relationship("Folder", back_populates="documents")
    snapshots = relationship("DailySnapshot", back_populates="document")
    revisions = relationship("RevisionEvent", back_populates="document")

class DailySnapshot(Base):
    __tablename__ = "daily_snapshots"
    id = Column(Integer, primary_key=True)
    document_id = Column(String, ForeignKey("documents.id"))
    date = Column(Date, nullable=False)
    total_words = Column(Integer, nullable=False)
    net_added = Column(Integer, default=0)       # Net added that day
    created_at = Column(DateTime, default=func.now())

    document = relationship("Document", back_populates="snapshots")
    # __table_args__ = ({"unique_constraint": ("document_id", "date")})

class RevisionEvent(Base):  # Append-only "event log" for changes (like game leaderboards history)
    __tablename__ = "revision_events"
    id = Column(Integer, primary_key=True)
    document_id = Column(String, ForeignKey("documents.id"))
    revision_id = Column(String)                   # Google revision ID (if needed)
    timestamp = Column(DateTime, default=func.now())
    words_added = Column(Integer, default=0)
    words_deleted = Column(Integer, default=0)
    net_change = Column(Integer)                   # added - deleted
    description = Column(Text, nullable=True)      # Optional: "Major edit", "AI paste?" etc.

    document = relationship("Document", back_populates="revisions")