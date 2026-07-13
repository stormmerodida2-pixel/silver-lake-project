import nh3

# Deliberately explicit rather than relying on nh3's own defaults, so this allowlist is the
# single source of truth and doesn't silently change behavior on an nh3 version bump.
ALLOWED_TAGS = {
    'p', 'br', 'strong', 'em', 'u',
    'h2', 'h3', 'h4',
    'ul', 'ol', 'li',
    'a', 'img', 'blockquote', 'code', 'pre',
}
ALLOWED_ATTRIBUTES = {
    'a': {'href', 'title', 'target'},
    'img': {'src', 'alt', 'title'},
}


def sanitize_body(raw_html):
    """Strips anything not on the allowlist - scripts, inline event handlers (onclick etc.,
    since they're simply never in ALLOWED_ATTRIBUTES for any tag), style/class attributes,
    iframes, forms. clean_content_tags removes a <script>/<style> tag's *content* too, not just
    the tag itself, so a submitted <script>alert(1)</script> doesn't survive as visible text."""
    return nh3.clean(
        raw_html or '',
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        clean_content_tags={'script', 'style'},
        link_rel='noopener noreferrer nofollow',
        url_schemes={'http', 'https', 'mailto'},
    )
