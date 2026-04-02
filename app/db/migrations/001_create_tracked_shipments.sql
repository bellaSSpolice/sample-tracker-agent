CREATE TABLE IF NOT EXISTS tracked_shipments (
    id              SERIAL PRIMARY KEY,
    tracking_number VARCHAR(100) NOT NULL,
    carrier         VARCHAR(50),
    tracking_url    TEXT,
    ship24_tracker_id VARCHAR(100),
    source_email_id VARCHAR(200),
    recipient_email VARCHAR(320),
    email_subject   VARCHAR(1000),
    email_sent_datetime TIMESTAMPTZ,
    matched_client_id UUID,
    matched_order_id  UUID,
    matched_sample_id UUID,
    current_status  VARCHAR(50) DEFAULT 'pending',
    status_detail   TEXT,
    delivered_datetime TIMESTAMPTZ,
    delivery_draft_created BOOLEAN DEFAULT FALSE,
    issue_draft_created    BOOLEAN DEFAULT FALSE,
    detected_at     TIMESTAMPTZ DEFAULT NOW(),
    last_checked_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Prevent duplicate tracking number per email
CREATE UNIQUE INDEX IF NOT EXISTS uix_tracked_shipments_tracking_email
    ON tracked_shipments (tracking_number, source_email_id);

-- Fast lookups for active shipments
CREATE INDEX IF NOT EXISTS ix_tracked_shipments_status
    ON tracked_shipments (current_status)
    WHERE current_status != 'delivered';
