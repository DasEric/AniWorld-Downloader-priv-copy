import base64
import binascii
import json
import logging
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import niquests

logger = logging.getLogger(__name__)

try:
    from ...models.common.subtitles import (
        MediaAsset,
        SubtitleTrack,
        normalize_subtitle_language,
    )
except ImportError:
    from h0melab.models.common.subtitles import (
        MediaAsset,
        SubtitleTrack,
        normalize_subtitle_language,
    )

try:
    from ...config import DEFAULT_USER_AGENT, GLOBAL_SESSION, PROVIDER_HEADERS_D
    from ...playwright.captcha import is_captcha_page, solve_captcha
except ImportError:
    from h0melab.config import DEFAULT_USER_AGENT, GLOBAL_SESSION, PROVIDER_HEADERS_D
    from h0melab.playwright.captcha import is_captcha_page, solve_captcha

# -----------------------------
# Precompiled regex patterns
# -----------------------------
REDIRECT_PATTERN = re.compile(r"""['"](\s*https?://[^'"<>\s]+/e/[^'"<>\s]+)['"]""")
B64_PATTERN = re.compile(r"var a168c='([^']+)'")
HLS_PATTERN = re.compile(r"'hls': '(?P<hls>[^']+)'")
VOE_SCRIPT_PATTERN = re.compile(
    r'<script type="application/json">\s*"(?:\\.|[^"\\])*"\s*</script>', re.DOTALL
)
JUNK_PARTS = ["@$", "^^", "~@", "%?", "*~", "!!", "#&"]
# Any direct playlist URL, used as a last-resort fallback.
M3U8_URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+?\.m3u8[^\s'\"<>]*")


def _voe_get(url, headers, timeout):
    """Fetch a VOE URL and return (text, final_url, status_code).

    Prefers curl_cffi with a real Chrome TLS fingerprint so we pass voe.sx's
    Cloudflare gate (the plain niquests session gets the challenge page instead,
    which is why the source could not be found). Falls back to the shared
    session when curl_cffi isn't installed.
    """
    try:
        from curl_cffi import requests as _curl_requests

        resp = _curl_requests.get(
            url,
            headers=headers,
            impersonate="chrome124",
            allow_redirects=True,
            timeout=timeout,
        )
        return resp.text, str(resp.url), resp.status_code
    except ImportError:
        pass
    except Exception as exc:
        logger.debug(f"VOE curl_cffi fetch failed ({exc}); using niquests")

    resp = GLOBAL_SESSION.get(url, headers=headers, timeout=timeout)
    return resp.text, str(resp.url), resp.status_code


# -----------------------------
# Helper functions
# -----------------------------
def shift_letters(input_str):
    """Apply ROT13 cipher to alphabetic characters."""
    result = []
    for c in input_str:
        code = ord(c)
        if 65 <= code <= 90:  # Uppercase A-Z
            code = (code - 65 + 13) % 26 + 65
        elif 97 <= code <= 122:  # Lowercase a-z
            code = (code - 97 + 13) % 26 + 97
        result.append(chr(code))
    return "".join(result)


def replace_junk(input_str):
    """Replace junk patterns with underscores."""
    for part in JUNK_PARTS:
        input_str = input_str.replace(part, "_")
    return input_str


def shift_back(s, n):
    """Shift characters back by n positions."""
    return "".join(chr(ord(c) - n) for c in s)


def decode_voe_string(encoded):
    """Decode VOE encoded string to a JSON object."""
    try:
        step1 = shift_letters(encoded)
        step2 = replace_junk(step1).replace("_", "")
        step3 = base64.b64decode(step2).decode()
        step4 = shift_back(step3, 3)
        step5 = base64.b64decode(step4[::-1]).decode()
        return json.loads(step5)
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as err:
        raise ValueError(f"Failed to decode VOE string: {err}") from err


def extract_voe_source_from_html(html):
    """Extract VOE video source — tries all known encoding variants."""
    # Variant 1: <script type="application/json"> with encoded payload
    try:
        script_blocks = re.findall(
            r'<script\s+type=["\']application/json["\']>(.*?)</script>', html, re.DOTALL
        )
        for script_block in script_blocks:
            encoded_text = script_block.strip()
            if encoded_text.startswith('"') and encoded_text.endswith('"'):
                encoded_text = encoded_text[1:-1]
            try:
                decoded = decode_voe_string(
                    encoded_text.encode().decode("unicode_escape")
                )
                source = decoded.get("source")
                if source:
                    return source
            except (ValueError, UnicodeDecodeError):
                continue
    except Exception:
        pass

    # Variant 2: var a168c='<encoded>' pattern
    try:
        m = B64_PATTERN.search(html)
        if m:
            decoded = decode_voe_string(m.group(1))
            source = decoded.get("source")
            if source:
                return source
    except Exception:
        pass

    # Variant 3: plain 'hls': '<url>' in page JS
    try:
        m = HLS_PATTERN.search(html)
        if m:
            return m.group("hls")
    except Exception:
        pass

    return None


def _decode_voe_payloads(html):
    """Return every decodable player payload, including the current JSON array form."""
    payloads = []
    blocks = re.findall(
        r'<script\s+type=["\']application/json["\']>(.*?)</script>', html, re.DOTALL
    )
    for block in blocks:
        value = block.strip()
        try:
            encoded_values = json.loads(value)
        except json.JSONDecodeError:
            encoded_values = value.strip('"')
        if isinstance(encoded_values, str):
            encoded_values = [encoded_values]
        if not isinstance(encoded_values, list):
            continue
        for encoded in encoded_values:
            if not isinstance(encoded, str):
                continue
            try:
                payloads.append(decode_voe_string(encoded))
            except ValueError:
                continue

    match = B64_PATTERN.search(html)
    if match:
        try:
            payloads.append(decode_voe_string(match.group(1)))
        except ValueError:
            pass
    return payloads


def _caption_track(caption, base_url, headers):
    if isinstance(caption, str):
        url = caption
        language = ""
        title = ""
        subtitle_format = ""
    elif isinstance(caption, dict):
        url = (
            caption.get("url")
            or caption.get("file")
            or caption.get("src")
            or caption.get("source")
            or caption.get("path")
        )
        language = (
            caption.get("language")
            or caption.get("lang")
            or caption.get("srclang")
            or caption.get("languageCode")
            or caption.get("countryCode")
            or caption.get("label")
        )
        title = caption.get("label") or caption.get("name") or caption.get("title") or ""
        subtitle_format = caption.get("format") or caption.get("type") or ""
    else:
        return None

    if not url:
        return None
    language = normalize_subtitle_language(language)
    if language == "none" and "deutsch" in str(title).lower():
        language = "deu"
    try:
        request_headers = dict(headers or {})
        parsed_base = urlparse(base_url)
        if parsed_base.scheme and parsed_base.netloc:
            request_headers["Referer"] = base_url
            request_headers["Origin"] = f"{parsed_base.scheme}://{parsed_base.netloc}"
        return SubtitleTrack(
            url=urljoin(base_url, str(url)),
            language=language,
            title=str(title),
            format=str(subtitle_format),
            headers=request_headers,
        )
    except ValueError:
        return None


def _payload_video_source(payload):
    """Return a direct source from VOE's compact or JWPlayer-style payload."""
    candidates = [payload.get("source")]
    sources = payload.get("sources") or []
    candidates.extend(sources if isinstance(sources, list) else [sources])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, dict):
            url = candidate.get("file") or candidate.get("url") or candidate.get("src")
            if url:
                return str(url)
    return None


def extract_voe_media_asset_from_html(html, base_url="", headers=None):
    """Extract the video URL and optional soft-caption tracks from a VOE player."""
    source = None
    tracks = []
    seen_tracks = set()
    for payload in _decode_voe_payloads(html):
        if not isinstance(payload, dict):
            continue
        source = source or _payload_video_source(payload)
        default_language = payload.get("default_captions_language") or ""
        captions = payload.get("captions")
        if captions is None:
            player_tracks = payload.get("tracks") or []
            if isinstance(player_tracks, dict):
                player_tracks = [player_tracks]
            elif not isinstance(player_tracks, list):
                player_tracks = []
            captions = [
                track
                for track in player_tracks
                if not isinstance(track, dict)
                or str(track.get("kind") or "captions").lower()
                in ("caption", "captions", "subtitle", "subtitles")
            ]
        if isinstance(captions, str):
            try:
                decoded_captions = json.loads(captions)
                captions = decoded_captions
            except json.JSONDecodeError:
                captions = [captions]
        if isinstance(captions, dict):
            normalized_captions = []
            for language, caption in captions.items():
                if isinstance(caption, str):
                    normalized_captions.append({"url": caption, "language": language})
                elif isinstance(caption, dict):
                    normalized_captions.append(
                        {"language": language, **caption}
                        if not caption.get("language")
                        else caption
                    )
            captions = normalized_captions
        if not isinstance(captions, (list, tuple)):
            captions = []
        for caption in captions:
            if isinstance(caption, dict) and not any(
                caption.get(key)
                for key in (
                    "language",
                    "lang",
                    "srclang",
                    "languageCode",
                    "countryCode",
                    "label",
                )
            ):
                caption = {**caption, "language": default_language}
            track = _caption_track(caption, base_url, headers)
            identity = (track.language, track.url) if track is not None else None
            if (
                track is not None
                and track.language != "none"
                and identity not in seen_tracks
            ):
                tracks.append(track)
                seen_tracks.add(identity)
    if source:
        return MediaAsset(str(source), tuple(tracks))
    source = extract_voe_source_from_html(html)
    return MediaAsset(source, ()) if source else None


# -----------------------------
# Main VOE functions
# -----------------------------
class _VOEUnavailable(ValueError):
    """The hoster reports a permanently missing video (404/410)."""


def get_media_asset_from_voe(embeded_voe_link, headers=None, max_retries=3, timeout=30):
    """Get the VOE video URL and every caption advertised by the same player."""
    parsed_embed_url = urlparse((embeded_voe_link or "").strip())
    if not parsed_embed_url.scheme or not parsed_embed_url.netloc:
        raise ValueError(f"Invalid VOE URL: {embeded_voe_link!r}")

    if headers is None:
        headers = PROVIDER_HEADERS_D.get("VOE", {"User-Agent": DEFAULT_USER_AGENT})

    # Enhanced headers for better compatibility
    enhanced_headers = {
        **headers,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    def fetch(url):
        result = _voe_get(url, enhanced_headers, timeout)
        if result[2] in (404, 410):
            raise _VOEUnavailable(f"VOE video unavailable (HTTP {result[2]}): {url}")
        return result

    for attempt in range(max_retries):
        try:
            # Add delay between retries
            if attempt > 0:
                wait_time = 2**attempt  # Exponential backoff: 2, 4, 8 seconds
                logger.warning(
                    f"Retry attempt {attempt + 1}/{max_retries}, waiting {wait_time}s..."
                )
                time.sleep(wait_time)

            # First request to VOE (curl_cffi impersonation, niquests fallback)
            html, final_url, status = fetch(embeded_voe_link)

            # Captcha on VOE page -> solve and retry this request
            if is_captcha_page(html, status):
                solve_captcha(embeded_voe_link)
                html, final_url, status = fetch(embeded_voe_link)

            # Try extracting source directly from the VOE embed page first
            asset = extract_voe_media_asset_from_html(
                html, final_url or embeded_voe_link, enhanced_headers
            )
            if asset:
                logger.info(f"VOE source extracted on attempt {attempt + 1}")
                return asset

            # Fallback: follow a redirect embedded in the page. VOE rotates the
            # embed domain, so accept an /e/ link on any host and also a plain
            # window.location redirect.
            redirect_match = REDIRECT_PATTERN.search(html) or re.search(
                r"""(?:location\.href|window\.location(?:\.href)?)\s*=\s*['"]"""
                r"""(https?://[^'"<>\s]+)['"]""",
                html,
            )
            if redirect_match:
                redirect_url = redirect_match.group(1).strip()
                try:
                    html2, final_url2, status2 = fetch(redirect_url)
                    if is_captcha_page(html2, status2):
                        solve_captcha(redirect_url)
                        html2, final_url2, status2 = fetch(redirect_url)
                    asset = extract_voe_media_asset_from_html(
                        html2, final_url2 or redirect_url, enhanced_headers
                    )
                    if asset:
                        return asset
                    m3u8 = M3U8_URL_PATTERN.search(html2)
                    if m3u8:
                        return MediaAsset(m3u8.group(0), ())
                except _VOEUnavailable:
                    raise
                except Exception as err:
                    logger.debug(f"VOE redirect fetch failed: {err}")

            # Last resort: a bare m3u8 URL anywhere on the original page.
            m3u8 = M3U8_URL_PATTERN.search(html)
            if m3u8:
                return MediaAsset(m3u8.group(0), ())

            raise ValueError("No VOE video source found in page.")

        except _VOEUnavailable:
            raise
        except (niquests.RequestException, Exception) as err:
            if attempt == max_retries - 1:
                raise ValueError(
                    f"Failed to fetch VOE page after {max_retries} attempts: {err}"
                ) from err
            logger.warning(f"Attempt {attempt + 1} failed: {str(err)[:100]}...")
            continue

    raise ValueError("Unexpected error in get_media_asset_from_voe")


def get_direct_link_from_voe(embeded_voe_link, headers=None, max_retries=3, timeout=30):
    """Backward-compatible direct-link API used by the other catalogue sites."""
    return get_media_asset_from_voe(
        embeded_voe_link,
        headers=headers,
        max_retries=max_retries,
        timeout=timeout,
    ).video_url


def get_preview_image_link_from_voe(embeded_voe_link, headers=None):
    """Get VOE preview image URL."""
    try:
        parsed_embed_url = urlparse((embeded_voe_link or "").strip())
        if not parsed_embed_url.scheme or not parsed_embed_url.netloc:
            raise ValueError(f"Invalid VOE URL: {embeded_voe_link!r}")

        if headers is None:
            headers = PROVIDER_HEADERS_D.get("VOE", {"User-Agent": DEFAULT_USER_AGENT})

        resp = GLOBAL_SESSION.get(embeded_voe_link, headers=headers)
        resp.raise_for_status()
        html = resp.text

        redirect_match = REDIRECT_PATTERN.search(html)
        if not redirect_match:
            raise ValueError("No redirect URL found in VOE response.")

        redirect_url = redirect_match.group(0)
        image_url = f"{redirect_url.replace('/e/', '/cache/')}_storyboard_L2.jpg"

        head_resp = GLOBAL_SESSION.head(
            image_url, headers=headers, allow_redirects=True
        )
        head_resp.raise_for_status()
        if "image" not in head_resp.headers.get("Content-Type", ""):
            raise ValueError("Preview image not reachable.")
        return image_url

    except niquests.RequestException as err:
        raise ValueError(f"Failed to fetch VOE preview image: {err}") from err


if __name__ == "__main__":
    # Tested on 2026/01/27 -> WORKING
    # Example: https://voe.sx/e/oa16zsjaqohr

    # logging.basicConfig(level=logging.DEBUG)

    link = input("Enter VOE Link: ").strip()
    if not link:
        print("Error: No link provided")
        sys.exit(1)

    try:
        print("=" * 25)

        direct_link = get_direct_link_from_voe(link)
        print("Direct link:", direct_link)
        print("=" * 25)

        print("Preview image:", get_preview_image_link_from_voe(link))
        print("=" * 25)

        print(f'mpv "{direct_link}" --user-agent="{DEFAULT_USER_AGENT}"')

        print("=" * 25)
    except ValueError as e:
        print("Error:", e)
