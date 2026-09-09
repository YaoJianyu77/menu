"""Conservative, offline selection of explicitly licensed recipe photographs.

Recipe prose licenses do not imply image rights. Supported records provide an
``image`` object or ``image_url`` plus image-specific rights fields. Unstructured
HTML/Markdown bodies are not scanned for photos: these can contain logos, other
recipes, tracking pixels or third-party photographs with unrelated licenses.
"""

from __future__ import annotations

from urllib.parse import urlsplit

IMAGE_LICENSES = {
    "CC0-1.0",
    "CC-BY-2.0",
    "CC-BY-3.0",
    "CC-BY-4.0",
    "CC-BY-SA-2.0",
    "CC-BY-SA-3.0",
    "CC-BY-SA-4.0",
    "CC-BY-NC-3.0",
    "CC-BY-NC-4.0",
    "CC-BY-NC-SA-3.0",
    "CC-BY-NC-SA-4.0",
    "PUBLIC-DOMAIN",
    "MIT",
}


def _public_url(value):
    if not isinstance(value, str) or any(char.isspace() for char in value):
        return False
    try:
        parts = urlsplit(value)
        return (
            parts.scheme in {"https", "http"}
            and bool(parts.hostname)
            and not parts.username
            and not parts.password
        )
    except ValueError:
        return False


def select_image(normalized, raw=None):
    """Return {url, source_url, attribution, license}, or None.

    Image-specific license and attribution, or explicit publication permission
    with its evidence URL, must be persisted. No recipe license fallback, URL
    invention, network request or source-record mutation is performed. A raw
    fallback must have the same stable identity as normalized.raw_id.
    """
    records = [normalized]
    if raw is not None and normalized.get("raw_id") == raw.get("id"):
        records.append(raw)
    for record in records:
        nested = record.get("image")
        image = nested if isinstance(nested, dict) else {}
        url = image.get("url") or record.get("image_url")
        source_url = image.get("source_url") or record.get("image_source_url")
        attribution = image.get("attribution") or record.get("image_attribution")
        license_name = image.get("license") or record.get("image_license")
        allowed = image.get("publication_allowed", record.get("image_publication_allowed"))
        permission = image.get("permission_evidence") or record.get("image_permission_evidence")
        if allowed is False or not _public_url(url) or not _public_url(source_url):
            continue
        licensed = isinstance(license_name, str) and license_name.upper() in IMAGE_LICENSES
        permission_granted = allowed is True and _public_url(permission)
        if not licensed and not permission_granted:
            continue
        if (
            licensed
            and license_name.upper() not in {"CC0-1.0", "PUBLIC-DOMAIN"}
            and (not isinstance(attribution, str) or not attribution.strip())
        ):
            continue
        return {
            "url": url,
            "source_url": source_url,
            "attribution": attribution or None,
            "license": license_name or "Explicit permission",
        }
    return None
