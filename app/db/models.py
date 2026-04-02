"""SQLAlchemy ORM models for tracked_shipments, email_scan_log, and read-only existing tables."""

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# ── New tables (we own these) ────────────────────────────────────────────────


class TrackedShipment(Base):
    __tablename__ = "tracked_shipments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tracking_number = Column(String(100), nullable=False)
    carrier = Column(String(50))
    tracking_url = Column(Text)
    ship24_tracker_id = Column(String(100))
    source_email_id = Column(String(200))
    recipient_email = Column(String(320))
    email_subject = Column(String(1000))
    email_sent_datetime = Column(DateTime(timezone=True))
    matched_client_id = Column(UUID(as_uuid=True))
    matched_order_id = Column(UUID(as_uuid=True))
    matched_sample_id = Column(UUID(as_uuid=True))
    current_status = Column(String(50), default="pending")
    status_detail = Column(Text)
    delivered_datetime = Column(DateTime(timezone=True))
    delivery_draft_created = Column(Boolean, default=False)
    issue_draft_created = Column(Boolean, default=False)
    detected_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_checked_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tracking_number", "source_email_id", name="uix_tracked_shipments_tracking_email"),
    )


class EmailScanLog(Base):
    __tablename__ = "email_scan_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gmail_message_id = Column(String(200), nullable=False, unique=True)
    email_subject = Column(String(1000))
    recipient_email = Column(String(320))
    sent_datetime = Column(DateTime(timezone=True))
    tracking_numbers_found = Column(Integer, default=0)
    scanned_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# ── Existing tables (read + update, never create/drop) ──────────────────────
# Mapped as read-only views into the existing Railway PostgreSQL schema.
# Only the columns we need are mapped.


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String)
    contact_email = Column(String)
    delivery_notification_enabled = Column(Boolean)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True)
    tracking_number = Column(String)
    shipping_carrier = Column(String)
    production_status = Column(String)
    delivered_date = Column(DateTime(timezone=True))
    client_id = Column(UUID(as_uuid=True))


class Sample(Base):
    __tablename__ = "samples"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True)
    tracking_number = Column(String)
    shipping_carrier = Column(String)
    status = Column(String)
    delivered_date = Column(DateTime(timezone=True))
    order_id = Column(UUID(as_uuid=True))


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True)
    order_id = Column(UUID(as_uuid=True))
    sample_id = Column(UUID(as_uuid=True))
    client_id = Column(UUID(as_uuid=True))
    notification_type = Column(String)
    status = Column(String)
