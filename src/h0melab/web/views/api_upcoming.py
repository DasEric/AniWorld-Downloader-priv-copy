"""Availability watchlist JSON endpoints."""
from sqlite3 import IntegrityError

from flask import jsonify, request

from ...config import LANG_LABELS
from .. import db, tmdb, upcoming
from ..media import WORKING_PROVIDERS


def _int(value, name):
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    return int(value)


def register(api):
    api.add_url_rule("/upcoming", view_func=upcoming_list, methods=["GET"])
    api.add_url_rule("/upcoming", view_func=upcoming_add, methods=["POST"])
    api.add_url_rule(
        "/upcoming/<int:movie_id>", view_func=upcoming_update, methods=["PATCH"]
    )
    api.add_url_rule(
        "/upcoming/<int:movie_id>", view_func=upcoming_delete, methods=["DELETE"]
    )
    api.add_url_rule(
        "/upcoming/tmdb/search", view_func=upcoming_search, methods=["GET"]
    )
    api.add_url_rule(
        "/upcoming/tmdb/movies", view_func=upcoming_browse, methods=["GET"]
    )
    api.add_url_rule("/upcoming/run", view_func=upcoming_run, methods=["POST"])


def upcoming_list():
    return jsonify(
        {
            "configured": tmdb.configured(),
            "items": db.list_upcoming_movies(),
            "last_run": db.upcoming_state_get("last_run"),
            "next_run": upcoming.next_run_at(),
            "checks_per_day": upcoming.settings_store.upcoming_checks_per_day(),
        }
    )


def upcoming_search():
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify({"error": "Search query is too short"}), 400
    media_type = request.args.get("type", "multi").strip().lower()
    if media_type not in ("movie", "tv", "multi"):
        return jsonify({"error": "Invalid media type"}), 400
    try:
        return jsonify({"items": tmdb.search_media(query, media_type)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


def upcoming_browse():
    try:
        return jsonify({"items": tmdb.upcoming_movies()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


def upcoming_add():
    data = request.get_json(silent=True) or {}
    try:
        media_type = str(data.get("media_type") or "movie").strip().lower()
        if media_type not in ("movie", "tv"):
            raise ValueError("Invalid media type")
        tmdb_id = _int(data.get("tmdb_id"), "tmdb_id")
        movie = (
            tmdb.movie_details(tmdb_id)
            if media_type == "movie"
            else tmdb.media_details(tmdb_id, media_type)
        )
        movie["media_type"] = media_type
        language = str(data.get("language") or "German Dub")
        provider = str(data.get("provider") or "VOE")
        if language not in LANG_LABELS.values():
            raise ValueError("Invalid language")
        if provider not in WORKING_PROVIDERS:
            raise ValueError("Invalid provider")
        custom_path_id = data.get("custom_path_id")
        if custom_path_id is not None:
            custom_path_id = _int(custom_path_id, "custom_path_id")
            if not db.get_custom_path(custom_path_id):
                raise ValueError("Invalid custom_path_id")
        movie_id = db.add_upcoming_movie(movie, language, provider, custom_path_id)
        return jsonify({"id": movie_id}), 201
    except IntegrityError:
        return jsonify({"error": "This title is already on the list"}), 409
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


def upcoming_update(movie_id):
    movie = db.get_upcoming_movie(movie_id)
    if not movie:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("waiting", "paused"):
        return jsonify({"error": "status must be waiting or paused"}), 400
    current = movie["status"]
    if status == "paused" and current not in ("waiting", "error"):
        return jsonify({"error": "Only waiting titles can be paused"}), 409
    if status == "waiting" and current != "paused":
        return jsonify({"error": "Only paused titles can be resumed"}), 409
    db.update_upcoming_movie(movie_id, status=status)
    return jsonify({"ok": True})


def upcoming_delete(movie_id):
    db.delete_upcoming_movie(movie_id)
    return "", 204


def upcoming_run():
    upcoming.run_async()
    return jsonify({"started": True}), 202
