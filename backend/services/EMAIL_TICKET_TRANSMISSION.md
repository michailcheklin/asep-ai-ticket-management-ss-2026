# Email Ticket Transmission

Outbound transfer of the **first public support-staff article** on a Zammad
ticket to a configured external recipient (Issue #195).

## Architecture decision

Mail is sent by the **backend via SMTP**, not through Zammad's notification
channel. Reasons:

- Durable duplicate protection needs a local unique constraint on
  `(ticket_id, recipient)` without adding Zammad tags or custom fields.
- The recipient is a configured address, not the ticket customer.
- The email body must contain only allowed fields and the triggering public
  article — not the full article history.
- Ticket data (articles, tags, status) must remain unchanged.

## Setup

1. Configure variables in `.env` (see top-level `example.env`):

   - `EMAIL_TICKET_TRANSMISSION_ENABLED=true`
   - `EMAIL_TICKET_TRANSMISSION_RECIPIENT=<deployment address>`
   - `EMAIL_TICKET_TRANSMISSION_WEBHOOK_SECRET=<shared secret>` (required when enabled)
   - SMTP: reuse `ZAMMAD_SMTP_*` / `ZAMMAD_SUPPORT_EMAIL`, or override with
     `EMAIL_SMTP_*`
   - Optional: `EMAIL_TICKET_TRANSMISSION_DB_PATH` (Docker default:
     `/data/email_ticket_transmissions.sqlite3` on volume `email-transmission-data`)

2. Restart `backend_app` (and re-run `zammad_bootstrap` so the article webhook
   trigger is created). The bootstrap wires
   `POST http://backend_app:8000/webhook/article-created` with HTTP Basic auth
   when the secret is set.

3. Authenticate webhook calls with one of:
   - Header `X-Webhook-Secret: <secret>`
   - `Authorization: Bearer <secret>`
   - HTTP Basic (password = secret)

If the feature is enabled without a valid recipient, the API responds with
HTTP 503 and a clear configuration error.

## Trigger conditions

After re-fetching the article from Zammad (webhook fields alone are not trusted):

- Ticket exists
- Article is public (`internal=false`)
- Sender is `Agent` (not Customer / System)
- Article is not a known chatbot handoff/solutions article
- No prior transmission row exists for `(ticket_id, normalized recipient)`

Only the first matching public support article triggers a send.

## Email content

Included: user name, user email, optional matrikel number, ticket number/id,
subject, optional Zammad link, body of the **triggering** public article.

Excluded: internal notes, other articles, secrets, technical config.

## Duplicate protection and statuses

SQLite table `email_ticket_transmissions` (see `backend/db/`) stores a row with
status `pending` **before** SMTP send. A unique constraint on
`(ticket_id, recipient_normalized)` makes concurrent webhooks safe: only one
insert succeeds.

| Status | Meaning | Auto-resend on later webhooks? |
|--------|---------|--------------------------------|
| `pending` | Reserved; send in progress or interrupted | **No** (row still holds the unique key) |
| `sent` | SMTP accepted the message | **No** |
| `uncertain` | SMTP outcome ambiguous (may already be delivered) | **No** (avoids duplicates) |
| `failed` | Clear SMTP failure before accept | **No** (same unique key; see manual retry) |

Issue #195 prioritises **at-most-once** delivery. There is **no** automatic SMTP
retry loop. `failed` is therefore also blocked by the unique constraint until an
operator intervenes. That matches “reserved / sent / uncertain must not resend”
and extends the same safety to clear failures so a later article event cannot
silently open a second send path.

### Safe manual retry (operators only)

Only after verifying in Mailpit/the mail server that **no** message with the
stored `message_id` was delivered:

1. Inspect the row (status, `triggering_article_id`, `error_message` class name).
2. Delete **only that** row, e.g.
   `DELETE FROM email_ticket_transmissions WHERE ticket_id = ? AND recipient_normalized = ?;`
3. Re-post the article-created webhook (or create a new eligible public agent
   article). A new `pending` reservation will be created and one send attempted.

Never delete `sent` or `uncertain` rows unless you intentionally accept a
possible duplicate. Prefer fixing SMTP/config first, then retry `failed` only.

## Production database / migration

- Runtime: SQLAlchemy `create_all` creates the table on first use if missing.
- Reference DDL: `backend/db/migrations/001_email_ticket_transmissions.sql`
  (must stay aligned with the ORM model; apply manually only if operators
  manage schema outside the app).
- Docker: persist `/data` via volume `email-transmission-data`.
- There is no Alembic pipeline yet; for a new environment, either start the
  backend once (`create_all`) or run the SQL file against the configured SQLite
  path before enabling the feature.

## Manual checks in real Zammad (before production enablement)

1. Confirm trigger **backend article transmission webhook** is active and
   condition `article.action` / `is` / `create` matches the UI for your Zammad
   version (this stack targets Zammad **7.0.x**; UI label may show “created”
   while the stored value is `create`).
2. Confirm webhook endpoint URL and Basic-Auth password (= shared secret).
3. Create a public agent article → backend logs show re-fetch + one send;
   Mailpit (or SMTP) receives exactly one message; ticket tags/status/articles
   unchanged aside from the article you created.
4. Create an internal note and a customer article → no mail.
5. Second public agent article on the same ticket → no second mail.
6. Replay the same webhook payload → still no second mail.
