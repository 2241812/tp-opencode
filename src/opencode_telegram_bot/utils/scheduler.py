from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Manage scheduled OpenCode tasks."""

    def __init__(self, max_tasks: int = 10) -> None:
        self.max_tasks = max_tasks
        self._scheduler = BackgroundScheduler(daemon=True)
        self._tasks: dict[str, dict[str, Any]] = {}
        self._callbacks: dict[str, Callable] = {}

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Task scheduler started")

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Task scheduler stopped")

    def register_callback(self, name: str, callback: Callable) -> None:
        self._callbacks[name] = callback

    def _wrap_callback(self, callback: Callable) -> Callable:
        if inspect.iscoroutinefunction(callback):
            def async_wrapper(*args, **kwargs):
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(callback(*args, **kwargs))
                except Exception:
                    logger.exception("Scheduled async task failed")
                finally:
                    loop.close()
            return async_wrapper
        return callback

    def add_interval_task(
        self,
        task_id: str,
        callback_name: str,
        prompt: str,
        interval_minutes: int,
        project_id: str = "",
        model_provider: str = "",
        model_id: str = "",
    ) -> bool:
        if len(self._tasks) >= self.max_tasks:
            logger.warning("Task limit reached (%d)", self.max_tasks)
            return False

        callback = self._callbacks.get(callback_name)
        if not callback:
            logger.error("Callback '%s' not found", callback_name)
            return False

        trigger = IntervalTrigger(minutes=interval_minutes)
        self._scheduler.add_job(
            self._wrap_callback(callback),
            trigger,
            args=[prompt, project_id, model_provider, model_id],
            id=task_id,
            replace_existing=True,
        )

        self._tasks[task_id] = {
            "callback_name": callback_name,
            "prompt": prompt,
            "interval_minutes": interval_minutes,
            "project_id": project_id,
            "model_provider": model_provider,
            "model_id": model_id,
            "type": "interval",
        }
        logger.info("Added interval task %s (every %dm)", task_id, interval_minutes)
        return True

    def add_cron_task(
        self,
        task_id: str,
        callback_name: str,
        prompt: str,
        cron_expression: str,
        project_id: str = "",
        model_provider: str = "",
        model_id: str = "",
    ) -> bool:
        if len(self._tasks) >= self.max_tasks:
            return False

        callback = self._callbacks.get(callback_name)
        if not callback:
            return False

        parts = cron_expression.split()
        if len(parts) == 5:
            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )
        else:
            logger.error("Invalid cron expression: %s", cron_expression)
            return False

        self._scheduler.add_job(
            self._wrap_callback(callback),
            trigger,
            args=[prompt, project_id, model_provider, model_id],
            id=task_id,
            replace_existing=True,
        )

        self._tasks[task_id] = {
            "callback_name": callback_name,
            "prompt": prompt,
            "cron_expression": cron_expression,
            "project_id": project_id,
            "model_provider": model_provider,
            "model_id": model_id,
            "type": "cron",
        }
        return True

    def remove_task(self, task_id: str) -> bool:
        try:
            self._scheduler.remove_job(task_id)
            self._tasks.pop(task_id, None)
            return True
        except Exception:
            return False

    def list_tasks(self) -> dict[str, dict[str, Any]]:
        return dict(self._tasks)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self._tasks.get(task_id)
