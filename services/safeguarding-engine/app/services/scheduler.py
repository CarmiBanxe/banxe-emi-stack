"""Celery beat scheduler for safeguarding tasks.

Scheduled tasks:
- Daily position calculation at 06:00 UTC
- Daily reconciliation at 07:00 UTC
- Monthly reconciliation on 1st of each month at 08:00 UTC
- Breach check for unresolved recon breaks >24h
"""

import logging
from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)


class SafeguardingScheduler:
    """Celery beat task scheduler."""

    @staticmethod
    def register_tasks(app: Celery) -> None:
        """Register periodic tasks with Celery beat."""
        app.conf.beat_schedule = {
            "daily-position-calculation": {
                "task": "safeguarding.tasks.calculate_daily_position",
                "schedule": crontab(hour=6, minute=0),  # 06:00 UTC
                "options": {"queue": "safeguarding"},
            },
            "daily-reconciliation": {
                "task": "safeguarding.tasks.run_daily_reconciliation",
                "schedule": crontab(hour=7, minute=0),  # 07:00 UTC
                "options": {"queue": "safeguarding"},
            },
            "monthly-reconciliation": {
                "task": "safeguarding.tasks.run_monthly_reconciliation",
                "schedule": crontab(day_of_month=1, hour=8, minute=0),
                "options": {"queue": "safeguarding"},
            },
            "breach-check-unresolved": {
                "task": "safeguarding.tasks.check_unresolved_breaks",
                "schedule": crontab(hour="*/4", minute=30),  # Every 4h
                "options": {"queue": "safeguarding"},
            },
        }
        logger.info("Safeguarding scheduled tasks registered")
