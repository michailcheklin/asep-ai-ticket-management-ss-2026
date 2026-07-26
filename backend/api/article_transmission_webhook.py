"""Authenticated Zammad webhook for email ticket transmission."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from ..config import (
    EMAIL_TICKET_TRANSMISSION_ENABLED,
    EMAIL_TICKET_TRANSMISSION_WEBHOOK_SECRET,
)
from ..services.BackendLoggingService import BackendLogger
from ..services.EmailTransmissionService import (
    EmailTransmissionConfigError,
    EmailTransmissionService,
)

zim_logger = BackendLogger("ArticleWebhook")
router = APIRouter()
_webhook_basic = HTTPBasic(auto_error=False)
email_transmission_service = EmailTransmissionService()


def verify_article_webhook_auth(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_webhook_basic)],
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Reject article-created webhooks without a valid shared secret."""
    expected = EMAIL_TICKET_TRANSMISSION_WEBHOOK_SECRET
    if not expected:
        zim_logger.error(
            "Article webhook rejected: EMAIL_TICKET_TRANSMISSION_WEBHOOK_SECRET is not configured"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook secret is not configured",
        )

    provided: str | None = None
    if x_webhook_secret:
        provided = x_webhook_secret.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    elif credentials is not None:
        provided = credentials.password or ""

    if not provided or not hmac.compare_digest(provided, expected):
        zim_logger.warning("Article webhook rejected: invalid or missing authentication")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing webhook authentication",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/webhook/article-created")
async def article_created(
    payload: dict,
    _: Annotated[None, Depends(verify_article_webhook_auth)],
):
    """
    Zammad webhook: first public support article may trigger email transmission.

    Authentication is required via ``X-Webhook-Secret``, ``Authorization: Bearer``,
    or HTTP Basic (password = shared secret). The ticket is never modified.
    """
    if not EMAIL_TICKET_TRANSMISSION_ENABLED:
        return {"status": "ignored", "reason": "disabled"}

    try:
        result = email_transmission_service.handle_article_created(payload)
    except EmailTransmissionConfigError as exc:
        zim_logger.error(f"Email transmission configuration error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        zim_logger.error(f"Article-created webhook failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transmission processing failed",
        ) from exc

    return {
        "status": result.status,
        "reason": result.reason,
        "ticket_id": result.ticket_id,
        "article_id": result.article_id,
        "transmission_id": result.transmission_id,
    }
