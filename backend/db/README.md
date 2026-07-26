"""Backend-owned SQLite persistence (not Zammad ticket data).

## Purpose

Zammad remains the system of record for tickets and articles. This package
stores only backend-controlled records that must not mutate Zammad, currently:

- `email_ticket_transmissions` — atomic duplicate protection for outbound
  email ticket transmission (Issue #195).

## Schema lifecycle

1. **Normal app start:** `init_db()` → SQLAlchemy `Base.metadata.create_all`
   creates missing tables. Safe to call repeatedly (no destructive migrations).
2. **Reference DDL:** `migrations/001_email_ticket_transmissions.sql` documents
   the same schema for operators and must stay in sync with `models.py`.
3. **Fresh production/SQLite volume:** either start `backend_app` once with the
   feature configured (preferred) or apply the SQL file to
   `EMAIL_TICKET_TRANSMISSION_DB_PATH` before enabling traffic.
4. **Docker:** compose mounts volume `email-transmission-data` at `/data` and
   sets `EMAIL_TICKET_TRANSMISSION_DB_PATH=/data/email_ticket_transmissions.sqlite3`.

There is no Alembic revision chain in this repository yet. Schema changes require
updating the ORM model, the SQL reference file, and a deliberate one-off
migration for existing deployments (backup the SQLite file first).
"""
