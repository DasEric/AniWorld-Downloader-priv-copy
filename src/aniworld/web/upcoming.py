"""Daily Upcoming watchlist checker with deliberately strict title matching."""

import re
import threading
import time
import unicodedata
from datetime import UTC, datetime, timedelta

from ..logger import get_logger
from . import db, media, settings_store, sitesearch, tmdb
from .media import WORKING_PROVIDERS

logger = get_logger(__name__)
_started = False
_start_lock = threading.Lock()
_run_lock = threading.Lock()


def _normalise(value):
    value = unicodedata.normalize("NFKD", value or "").casefold()
    return re.sub(r"[^a-z0-9]+", "", value)


def _exact_hit(movie):
    titles = list(
        dict.fromkeys(filter(None, (movie["title"], movie.get("original_title", ""))))
    )
    aliases = {_normalise(value) for value in titles} - {""}
    candidates = []
    for site in sitesearch.MOVIE_SITES:
        if not settings_store.site_enabled(site):
            continue
        for readable in titles:
            for hit in sitesearch.search(site, readable):
                # Cineby movie URLs carry the authoritative TMDB id.
                if site == "cineby" and re.search(
                    rf"/movie/{movie['tmdb_id']}(?:[/?#]|$)", hit["url"]
                ):
                    return hit
                if _normalise(hit.get("title")) in aliases:
                    try:
                        from ..providers import resolve_provider

                        found = resolve_provider(hit["url"]).series_cls(url=hit["url"])
                        year = str(getattr(found, "release_year", ""))[:4]
                    except Exception:
                        year = ""
                    if year != str(movie["release_year"]):
                        continue
                    candidates.append(hit)
    # Every candidate reaching this point has the exact title and year. Prefer
    # the first enabled site instead of stalling forever when several sites
    # carry the same confirmed movie.
    unique = {hit["url"]: hit for hit in candidates}
    return next(iter(unique.values()), None)


def _usable_provider(url, language, preferred):
    from ..providers import resolve_provider

    resolved = resolve_provider(url)
    episode = resolved.episode_cls(url=url, selected_language=language)
    if resolved.name == "Cineby":
        available = (
            ["Cineby"]
            if language in getattr(episode, "available_language_labels", ())
            else []
        )
    else:
        available = media.provider_map(episode.provider_data).get(language, [])
    if preferred in available:
        return preferred
    return available[0] if available else None


def run_cycle():
    if not tmdb.configured() or not _run_lock.acquire(blocking=False):
        return False
    try:
        now = datetime.now(UTC).replace(microsecond=0).isoformat()
        for movie in db.list_upcoming_movies():
            if movie["status"] in ("paused", "queued", "downloaded"):
                continue
            if movie["release_date"] > datetime.now(UTC).date().isoformat():
                continue
            try:
                hit = _exact_hit(movie)
                if not hit:
                    db.update_upcoming_movie(
                        movie["id"],
                        status="waiting",
                        last_checked_at=now,
                        last_message="No unique exact match yet",
                    )
                    continue
                preferred = (
                    movie["provider"]
                    if movie["provider"] in WORKING_PROVIDERS
                    else WORKING_PROVIDERS[0]
                )
                provider = _usable_provider(hit["url"], movie["language"], preferred)
                if not provider:
                    db.update_upcoming_movie(
                        movie["id"],
                        status="waiting",
                        last_checked_at=now,
                        last_message="Exact title found, but no usable provider for the language",
                    )
                    continue
                queue_id = db.add_to_queue(
                    movie["title"],
                    hit["url"],
                    [hit["url"]],
                    movie["language"],
                    provider,
                    custom_path_id=movie["custom_path_id"],
                    source="upcoming",
                )
                db.update_upcoming_movie(
                    movie["id"],
                    status="queued",
                    matched_url=hit["url"],
                    queue_id=queue_id,
                    last_checked_at=now,
                    last_message="Unique exact match queued",
                )
            except Exception as exc:
                logger.warning(
                    "Upcoming check failed for movie %s: %s", movie["id"], exc
                )
                db.update_upcoming_movie(
                    movie["id"],
                    status="error",
                    last_checked_at=now,
                    last_message=str(exc)[:500],
                )
        db.upcoming_state_set("last_run", now)
        db.upcoming_state_set(
            "next_run",
            (datetime.now(UTC) + timedelta(days=1)).replace(microsecond=0).isoformat(),
        )
        return True
    finally:
        _run_lock.release()


def run_async():
    threading.Thread(
        target=run_cycle, name="aniworld-upcoming-manual", daemon=True
    ).start()


def ensure_started():
    global _started
    with _start_lock:
        if _started:
            return
        _started = True

    def loop():
        while True:
            try:
                last = db.upcoming_state_get("last_run")
                due = True
                if last:
                    try:
                        parsed = datetime.fromisoformat(last)
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=UTC)
                        due = datetime.now(UTC) - parsed >= timedelta(days=1)
                    except (TypeError, ValueError):
                        pass
                if due:
                    run_cycle()
            except Exception:
                logger.exception("Upcoming scheduler cycle failed")
            time.sleep(300)

    threading.Thread(target=loop, name="aniworld-upcoming", daemon=True).start()
