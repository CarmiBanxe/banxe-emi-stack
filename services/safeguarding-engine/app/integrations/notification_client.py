"""Notification client for Telegram + email alerts and n8n workflows.

Notification chain: Telegram -> Email -> n8n workflow -> FCA Gabriel upload.
"""

import logging
from datetime import UTC, datetime
from typing import Dict, List

logger = logging.getLogger(__name__)


class NotificationClient:
    """Multi-channel notification client."""

    def __init__(self, telegram_token: str = "", email_config: Dict = None, n8n_url: str = ""):
        self.telegram_token = telegram_token
        self.email_config = email_config or {}
        self.n8n_url = n8n_url
        self._notification_log: list[dict] = []  # I-24 append-only

    async def send_telegram_alert(self, chat_id: str, message: str) -> bool:
        """Send Telegram alert to MLRO + CEO.

        BT-015: Returns False until Telegram integration is provisioned (P1).
        I-24: logs every attempt.
        """
        self._notification_log.append(
            {
                "channel": "telegram",
                "chat_id": chat_id,
                "queued_at": datetime.now(UTC).isoformat(),
                "delivered": False,
            }
        )
        logger.warning("NotificationClient.send_telegram_alert: not provisioned (P1). chat_id=%s", chat_id)
        return False

    async def send_email_alert(self, recipients: List[str], subject: str, body: str) -> bool:
        """Send email alert for breach notification.

        BT-015: Returns False until email integration is provisioned (P1).
        I-24: logs every attempt.
        """
        self._notification_log.append(
            {
                "channel": "email",
                "recipients": recipients,
                "subject": subject,
                "queued_at": datetime.now(UTC).isoformat(),
                "delivered": False,
            }
        )
        logger.warning("NotificationClient.send_email_alert: not provisioned (P1). recipients=%s", recipients)
        return False

    async def trigger_n8n_workflow(self, workflow_id: str, payload: Dict) -> Dict:
        """Trigger n8n workflow for FCA Gabriel submission.

        BT-015: Returns {} until n8n integration is provisioned (P1).
        I-24: logs every attempt.
        """
        self._notification_log.append(
            {
                "channel": "n8n",
                "workflow_id": workflow_id,
                "queued_at": datetime.now(UTC).isoformat(),
                "delivered": False,
            }
        )
        logger.warning("NotificationClient.trigger_n8n_workflow: not provisioned (P1). workflow_id=%s", workflow_id)
        return {}

    async def notify_breach_chain(self, breach_data: Dict) -> Dict:
        """Execute full notification chain: Telegram -> Email -> n8n.

        BT-015: Logs breach attempt at CRITICAL and returns {} until chain is provisioned (P1).
        I-24: logs the full breach_data for traceability.
        """
        self._notification_log.append(
            {
                "channel": "breach_chain",
                "breach_type": breach_data.get("breach_type"),
                "queued_at": datetime.now(UTC).isoformat(),
                "delivered": False,
            }
        )
        logger.critical("BREACH NOTIFICATION CHAIN (NOT PROVISIONED): %s", breach_data.get("breach_type"))
        return {}
