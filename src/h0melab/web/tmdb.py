"""Small, fixed-origin TMDB client. Credentials never leave this module."""

import os
from datetime import UTC, datetime

import niquests as requests

from .settings_store import TMDB_KEY

BASE_URL = "https://api.themoviedb.org/3"


class TMDBError(RuntimeError):
    pass


def configured():
    return bool(os.environ.get(TMDB_KEY, "").strip())


def _get(path, **params):
    token = os.environ.get(TMDB_KEY, "").strip()
    if not token:
        raise TMDBError("TMDB is not configured")
    headers = {"Accept": "application/json", "User-Agent": "H0melab Downloader"}
    if token.startswith("eyJ") or len(token) > 64:
        headers["Authorization"] = f"Bearer {token}"
    else:
        params["api_key"] = token
    try:
        response = requests.get(
            f"{BASE_URL}/{path.lstrip('/')}",
            params=params,
            headers=headers,
            timeout=15,
        )
    except Exception as exc:
        raise TMDBError("TMDB request failed") from exc
    if response.status_code in (401, 403):
        raise TMDBError("TMDB rejected the configured key")
    if not 200 <= response.status_code < 300:
        raise TMDBError(f"TMDB request failed ({response.status_code})")
    try:
        return response.json()
    except ValueError as exc:
        raise TMDBError("TMDB returned an invalid response") from exc


def _movie(item):
    release = item.get("release_date") or ""
    return {
        "tmdb_id": int(item["id"]),
        "title": item.get("title") or item.get("original_title") or "Unknown",
        "original_title": item.get("original_title") or "",
        "release_date": release,
        "release_year": int(release[:4])
        if len(release) >= 4 and release[:4].isdigit()
        else 0,
        "poster_path": item.get("poster_path"),
        "overview": item.get("overview") or "",
        "media_type": "movie",
    }


def _series(item):
    release = item.get("first_air_date") or ""
    return {
        "tmdb_id": int(item["id"]),
        "title": item.get("name") or item.get("original_name") or "Unknown",
        "original_title": item.get("original_name") or "",
        "release_date": release,
        "release_year": int(release[:4])
        if len(release) >= 4 and release[:4].isdigit()
        else 0,
        "poster_path": item.get("poster_path"),
        "overview": item.get("overview") or "",
        "media_type": "tv",
    }


def search_movies(query, language="de-DE"):
    data = _get("search/movie", query=query, language=language, include_adult="false")
    return [_movie(item) for item in data.get("results", []) if item.get("id")]


def search_media(query, media_type="multi", language="de-DE"):
    if media_type not in ("movie", "tv", "multi"):
        raise TMDBError("Invalid media type")
    path = "search/multi" if media_type == "multi" else f"search/{media_type}"
    data = _get(path, query=query, language=language, include_adult="false")
    results = []
    for item in data.get("results", []):
        kind = item.get("media_type") or media_type
        if not item.get("id") or kind not in ("movie", "tv"):
            continue
        results.append(_movie(item) if kind == "movie" else _series(item))
    return results


def upcoming_movies(language="de-DE"):
    data = _get("movie/upcoming", language=language, region="DE")
    today = datetime.now(UTC).date().isoformat()
    return [
        _movie(item)
        for item in data.get("results", [])
        if (item.get("release_date") or "") >= today
    ]


def movie_details(tmdb_id, language="de-DE"):
    if not isinstance(tmdb_id, int) or tmdb_id <= 0:
        raise TMDBError("Invalid TMDB movie id")
    return _movie(_get(f"movie/{tmdb_id}", language=language))


def media_details(tmdb_id, media_type="movie", language="de-DE"):
    if not isinstance(tmdb_id, int) or tmdb_id <= 0:
        raise TMDBError("Invalid TMDB id")
    if media_type == "movie":
        return _movie(_get(f"movie/{tmdb_id}", language=language))
    if media_type == "tv":
        return _series(_get(f"tv/{tmdb_id}", language=language))
    raise TMDBError("Invalid media type")
