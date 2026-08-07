from celery import Celery

from .config import get_settings

settings = get_settings()
celery_app = Celery(
    "data_studio_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="data_studio.healthcheck")  # type: ignore[untyped-decorator]
def healthcheck() -> dict[str, str]:
    """A deployment smoke task; ingestion moves here in the next vertical slice."""

    return {"status": "ok"}
