"""Shared subtitle metadata and download helpers.

Subtitle discovery stays in the hoster extractors.  This module only provides
the small, provider-neutral value objects used by the download pipeline.
"""

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import niquests

_GERMAN_CODES = {"de", "de-de", "deu", "ger", "german", "deutsch"}


def normalize_subtitle_language(value):
    """Return the canonical ISO-639-2 code used in media containers."""
    text = str(value or "").strip().lower().replace("_", "-")
    if text in ("", "none", "off", "no", "false"):
        return "none"
    if (
        text in _GERMAN_CODES
        or text.startswith(("de-", "deutsch", "german"))
    ):
        return "deu"
    return text


@dataclass(frozen=True)
class SubtitleTrack:
    url: str
    language: str
    title: str = ""
    format: str = ""
    headers: dict = field(default_factory=dict, compare=False)

    def __post_init__(self):
        parsed = urlparse(str(self.url or "").strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"Invalid subtitle URL: {self.url!r}")
        object.__setattr__(self, "language", normalize_subtitle_language(self.language))

    @property
    def suffix(self):
        candidate = (self.format or Path(urlparse(self.url).path).suffix).lower()
        if candidate and not candidate.startswith("."):
            candidate = f".{candidate}"
        return candidate if candidate in (".vtt", ".srt", ".ass", ".ssa") else ".vtt"


@dataclass(frozen=True)
class MediaAsset:
    video_url: str
    subtitles: tuple[SubtitleTrack, ...] = ()

    def subtitle(self, language):
        wanted = normalize_subtitle_language(language)
        return next((track for track in self.subtitles if track.language == wanted), None)


def download_subtitle(track, output_path, timeout=30):
    """Download one external caption track using its player request headers."""
    output_path = Path(output_path)
    response = niquests.get(
        track.url,
        headers=dict(track.headers or {}),
        timeout=timeout,
    )
    response.raise_for_status()
    content = response.content or b""
    if not content.strip():
        raise ValueError("Subtitle response is empty")
    output_path.write_bytes(content)
    return output_path
