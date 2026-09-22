"""Resolve the XFileSharing player used by moflix-stream.click."""

import json
import re
from urllib.parse import urljoin, urlparse

from curl_cffi import requests

from ...models.common.hls import _parse_master_playlist, _select_audio_rendition
from .filemoon import _unpack_js

_PACKED_PLAYER = re.compile(
    r"eval\(function\(p,a,c,k,e,d\).*?\}\('(?P<p>(?:\\.|[^'\\])*)',"
    r"\s*(?P<radix>\d+),\s*\d+,\s*'(?P<keywords>(?:\\.|[^'\\])*)'"
    r"\.split\('\|'\)\)\)",
    re.DOTALL,
)
_LINKS = re.compile(r"var\s+links\s*=\s*(\{[^}]+\})")


_HLS_HEADERS = {
    "Referer": "https://moflix-stream.click/",
    "Accept-Encoding": "identity",
}


def _fetch_playlist(url):
    response = requests.get(
        url,
        impersonate="chrome124",
        headers=_HLS_HEADERS,
        timeout=8,
    )
    response.raise_for_status()
    return response.text or ""


def _probe_segment(playlist_url, playlist):
    """Read only the start of one segment to catch dead CDN origins early."""
    segment = next(
        (
            line.strip()
            for line in playlist.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ),
        None,
    )
    if not segment:
        return False
    url = urljoin(playlist_url, segment)
    if urlparse(url).scheme != "https":
        return False

    response = requests.get(
        url,
        impersonate="chrome124",
        headers=_HLS_HEADERS,
        timeout=8,
        stream=True,
    )
    try:
        try:
            response.raise_for_status()
        except Exception as exc:
            status = getattr(response, "status_code", None)
            if status is not None and status >= 400:
                raise ValueError(f"media segment returned HTTP {status}") from exc
            raise
        chunk = next((part for part in response.iter_content() if part), b"")
        return bool(chunk) and not chunk.lstrip().lower().startswith(
            (b"<html", b"<!doctype html")
        )
    finally:
        response.close()


def _has_media(url, playlist, depth=0):
    """Check the selected video and German audio renditions, not just the master."""
    if depth > 2 or not playlist.lstrip().startswith("#EXTM3U"):
        return False
    if "#EXT-X-STREAM-INF" not in playlist:
        return _probe_segment(url, playlist)

    variants, renditions = _parse_master_playlist(playlist, url)
    if not variants:
        return False
    variant = max(variants, key=lambda item: item.bandwidth)
    rendition = _select_audio_rendition(renditions, variant.audio_group, "deu")
    children = [variant.uri]
    if rendition is not None:
        children.append(rendition.uri)
    for child_url in children:
        if urlparse(child_url).scheme != "https":
            return False
        if not _has_media(child_url, _fetch_playlist(child_url), depth + 1):
            return False
    return True


def get_direct_links_from_moflixclick(embed_url):
    """Return usable player HLS mirrors in the player's priority order."""
    parsed = urlparse(embed_url or "")
    if parsed.scheme != "https" or parsed.hostname != "moflix-stream.click":
        raise ValueError("Invalid MoflixClick embed URL")

    response = requests.get(embed_url, impersonate="chrome124", timeout=20)
    response.raise_for_status()
    match = _PACKED_PLAYER.search(response.text or "")
    if match is None:
        raise ValueError("MoflixClick player data not found")

    unpacked = _unpack_js(
        match.group("p").replace("\\'", "'"),
        int(match.group("radix")),
        0,
        match.group("keywords").split("|"),
    )
    links_match = _LINKS.search(unpacked)
    if links_match is None:
        raise ValueError("MoflixClick stream links not found")
    links = json.loads(links_match.group(1))
    # The player tries hls4, hls3, then hls2. A 200 response with a valid
    # master is not enough: child playlists may return HTML or empty data.
    last_error = None
    usable = []
    failures = []
    for key in ("hls4", "hls3", "hls2"):
        raw_url = links.get(key)
        if isinstance(raw_url, str) and raw_url.strip():
            # The player also emits protocol-relative and path-relative HLS
            # links. Dropping them made an otherwise working hoster appear to
            # have no reachable playlist at all.
            url = urljoin(embed_url, raw_url.strip())
            if urlparse(url).scheme != "https":
                continue
            try:
                if _has_media(url, _fetch_playlist(url)):
                    if url not in usable:
                        usable.append(url)
                else:
                    last_error = ValueError(f"{key} has no usable HLS media playlist")
                    failures.append(f"{key}: invalid playlist or media segment")
            except Exception as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and status >= 400:
                    reason = f"HTTP {status}"
                elif isinstance(exc, ValueError) and str(exc).startswith(
                    "media segment returned HTTP "
                ):
                    reason = str(exc)
                else:
                    reason = type(exc).__name__
                failures.append(f"{key}: {reason}")
    if usable:
        return tuple(usable)
    details = "; ".join(failures) if failures else "no HLS links in the player"
    raise ValueError(f"MoflixClick has no playable HLS mirror ({details})") from last_error


def get_direct_link_from_moflixclick(embed_url):
    return get_direct_links_from_moflixclick(embed_url)[0]
