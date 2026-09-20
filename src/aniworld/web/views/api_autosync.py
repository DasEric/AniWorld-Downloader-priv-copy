"""AutoSync status, tracked series and the manual Sync now trigger."""

import sqlite3
import threading

from flask import abort, jsonify, request

from ...logger import get_logger
from .. import autosync, db
from ..settings_store import autosync_enabled

logger = get_logger(__name__)


def register(bp):
    bp.add_url_rule("/autosync/status", view_func=autosync_status)
    bp.add_url_rule("/autosync/run", view_func=autosync_run, methods=["POST"])
    bp.add_url_rule("/autosync/series", view_func=list_series)
    bp.add_url_rule("/autosync/series", view_func=add_series, methods=["POST"])
    bp.add_url_rule("/autosync/series/state", view_func=series_state)
    bp.add_url_rule(
        "/autosync/series/<int:series_id>",
        view_func=update_series,
        methods=["PATCH"],
    )
    bp.add_url_rule(
        "/autosync/series/<int:series_id>",
        view_func=delete_series,
        methods=["DELETE"],
    )
    bp.add_url_rule("/autosync/exclusions", view_func=list_exclusions)
    bp.add_url_rule("/autosync/exclusions", view_func=add_exclusion, methods=["POST"])
    bp.add_url_rule(
        "/autosync/exclusions/<int:exclusion_id>",
        view_func=delete_exclusion,
        methods=["DELETE"],
    )
    # Legacy exclusion endpoints remain readable for compatibility with older
    # clients and databases. The explicit subscription engine ignores them.
    bp.add_url_rule("/autosync/excluded", view_func=exclusion_state)
    bp.add_url_rule(
        "/autosync/excluded", view_func=set_exclusion_state, methods=["POST"]
    )


def _guard():
    if not autosync_enabled():
        abort(404)


def autosync_status():
    _guard()
    return jsonify(autosync.status())


def autosync_run():
    """Kick off a cycle in the background so the request returns immediately."""
    _guard()
    if autosync.is_running():
        return jsonify({"error": "A sync is already running"}), 409

    threading.Thread(
        target=_run_quietly, name="aniworld-autosync-manual", daemon=True
    ).start()
    return jsonify({"ok": True, "started": True})


def _run_quietly():
    try:
        autosync.run_cycle()
    except RuntimeError as exc:
        logger.info("AutoSync manual run skipped: %s", exc)
    except Exception:
        logger.exception("AutoSync manual run failed")


def list_series():
    _guard()
    return jsonify({"series": db.get_autosync_series()})


def series_state():
    """Return the row represented by the series modal's current selections."""
    _guard()
    series_url = request.args.get("url")
    language = (request.args.get("language") or "").strip()
    raw_path_id = request.args.get("custom_path_id")
    try:
        canonical_url, site = autosync.canonical_series_url(series_url)
        if language not in autosync.SITE_LANGUAGES[site]:
            raise ValueError(f"Language {language!r} is not supported for this site.")
        custom_path_id = None if raw_path_id in (None, "") else int(raw_path_id)
        if custom_path_id is not None and custom_path_id <= 0:
            raise ValueError("custom_path_id must be a positive integer.")
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    item = db.find_autosync_series(canonical_url, language, custom_path_id)
    return jsonify({"tracked": item is not None, "series": item})


def add_series():
    _guard()
    data = request.get_json(silent=True) or {}
    language = data.get("language")
    if not isinstance(language, str):
        return jsonify({"error": "language must be a string."}), 400
    try:
        item = autosync.add_subscription(
            series_url=data.get("series_url"),
            language=language.strip(),
            provider=data.get("provider"),
            custom_path_id=data.get("custom_path_id"),
        )
    except (sqlite3.IntegrityError, autosync.DuplicateSubscription):
        return jsonify({"error": "This series copy is already in Auto-Sync."}), 409
    except (TypeError, ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "series": item}), 201


def update_series(series_id):
    _guard()
    data = request.get_json(silent=True) or {}
    values = {}
    if "enabled" in data:
        if not isinstance(data["enabled"], bool):
            return jsonify({"error": "enabled must be a boolean."}), 400
        if data["enabled"]:
            item = db.get_autosync_series_item(series_id)
            if not item:
                return jsonify({"error": "Auto-Sync entry not found."}), 404
            try:
                autosync._ensure_copy_is_unique(
                    item["series_url"],
                    item["language"],
                    item.get("custom_path_id"),
                    current_id=series_id,
                )
            except RuntimeError as exc:
                return jsonify({"error": str(exc)}), 409
        values["enabled"] = int(data["enabled"])
    if "provider" in data:
        try:
            values["provider"] = autosync._validated_provider(data["provider"])
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
    if not values:
        return jsonify({"error": "No supported changes supplied."}), 400
    if not db.update_autosync_series(series_id, **values):
        return jsonify({"error": "Auto-Sync entry not found."}), 404
    return jsonify({"ok": True, "series": db.get_autosync_series_item(series_id)})


def delete_series(series_id):
    _guard()
    if not db.remove_autosync_series(series_id):
        return jsonify({"error": "Auto-Sync entry not found."}), 404
    return jsonify({"ok": True})


def list_exclusions():
    _guard()
    return jsonify({"exclusions": db.get_autosync_exclusions()})


def add_exclusion():
    _guard()
    data = request.get_json(silent=True) or {}
    series_url = (data.get("series_url") or "").strip()
    if not series_url:
        return jsonify({"error": "series_url is required"}), 400
    db.add_autosync_exclusion(series_url, (data.get("title") or "").strip())
    return jsonify({"ok": True})


def delete_exclusion(exclusion_id):
    _guard()
    db.remove_autosync_exclusion(exclusion_id=exclusion_id)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Legacy exclusion state
# ---------------------------------------------------------------------------
def exclusion_state():
    _guard()
    series_url = (request.args.get("url") or "").strip()
    if not series_url:
        return jsonify({"error": "url is required"}), 400
    return jsonify({"excluded": db.is_autosync_excluded(series_url)})


def set_exclusion_state():
    _guard()
    data = request.get_json(silent=True) or {}
    series_url = (data.get("series_url") or "").strip()
    if not series_url:
        return jsonify({"error": "series_url is required"}), 400

    if data.get("excluded"):
        db.add_autosync_exclusion(series_url, (data.get("title") or "").strip())
    else:
        db.remove_autosync_exclusion(series_url=series_url)
    return jsonify({"ok": True})
