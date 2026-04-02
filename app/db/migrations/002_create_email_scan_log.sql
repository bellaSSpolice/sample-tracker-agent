CREATE TABLE IF NOT EXISTS email_scan_log (
    id                    SERIAL PRIMARY KEY,
    gmail_message_id      VARCHAR(200) NOT NULL,
    email_subject         VARCHAR(1000),
    recipient_email       VARCHAR(320),
    sent_datetime         TIMESTAMPTZ,
    tracking_numbers_found INTEGER DEFAULT 0,
    scanned_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uix_email_scan_log_gmail_id
    ON email_scan_log (gmail_message_id);
