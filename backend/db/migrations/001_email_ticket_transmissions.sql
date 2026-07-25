-- Email ticket transmission duplicate-protection table.
-- Applied automatically via SQLAlchemy create_all on first use.
-- Kept here for documentation and manual/ops review.

CREATE TABLE IF NOT EXISTS email_ticket_transmissions (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    recipient_normalized VARCHAR(320) NOT NULL,
    triggering_article_id INTEGER NOT NULL,
    message_id VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL,
    sent_at DATETIME,
    error_message TEXT,
    CONSTRAINT uq_email_transmission_ticket_recipient
        UNIQUE (ticket_id, recipient_normalized)
);

CREATE INDEX IF NOT EXISTS ix_email_ticket_transmissions_ticket_id
    ON email_ticket_transmissions (ticket_id);
