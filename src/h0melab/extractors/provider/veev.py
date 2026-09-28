"""Resolve Veev embeds through the site's JavaScript player handshake."""

from urllib.parse import urlparse


def get_direct_link_from_veev(embed_url):
    parsed = urlparse(embed_url or "")
    if parsed.scheme != "https" or parsed.hostname not in {"veev.to", "www.veev.to"}:
        raise ValueError("Invalid Veev embed URL")

    from ...playwright.captcha import playwright_get_veev_stream_url

    stream_url = playwright_get_veev_stream_url(embed_url)
    if not stream_url:
        raise ValueError("Veev player returned no playable video URL")
    return stream_url
