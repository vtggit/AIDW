"""Issue #811 — freeform proof: SPA/static responses are never served stale.

Proves, from ``app/nginx.conf`` itself (location blocks located by matching
braces, not line positions):

* AC-1/AC-3: ``location /`` — which serves the SPA pages, scripts,
  stylesheets and images, the ``try_files`` ``index.html`` fallback, and every
  request rewritten in from the ``/app/`` prefix — carries
  ``add_header Cache-Control "no-cache" always;`` so the header is sent for
  every status.  ``location /api/`` has no ``Cache-Control`` header of its
  own, and the server level adds none either (nginx only inherits ``add_header``
  into a level that defines none of its own), so ``/api/`` responses are left
  to the backend's own headers.
* AC-2: every other directive of every location block is exactly the one from
  the base branch, as listed in ``EXPECTED_LOCATION_DIRECTIVES`` below — the
  only delta is the ``no-cache`` line gained by ``location /``.
"""

import os
import re

_NGINX_CONF = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "app", "nginx.conf"
    )
)

# Every directive of every location block, exactly as on the base branch —
# except that ``location /`` additionally gains the ``no-cache`` header this
# issue requires.  Any added, removed or reordered directive fails the test.
EXPECTED_LOCATION_DIRECTIVES = {
    "/app/": [
        "rewrite ^/app/(.*)$ /$1 last;",
    ],
    "/": [
        "try_files $uri $uri/ /index.html;",
        'add_header Cache-Control "no-cache" always;',
    ],
    "/api/": [
        "proxy_pass http://backend:9000;",
        "proxy_set_header Host $host;",
        "proxy_set_header X-Real-IP $remote_addr;",
        "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "proxy_set_header X-Forwarded-Proto $scheme;",
    ],
    "/assistant/": [
        "resolver 127.0.0.11 valid=10s;",
        "set $assistant_upstream http://aidw-assistant:9020;",
        "proxy_pass $assistant_upstream$request_uri;",
        "proxy_set_header Host $host;",
        "proxy_set_header X-Real-IP $remote_addr;",
        "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "proxy_set_header X-Forwarded-Proto $scheme;",
        "proxy_buffering off;",
        "proxy_cache off;",
        "proxy_read_timeout 300s;",
    ],
}


def _strip_nginx_comments(text: str) -> str:
    """Drop ``#`` comments from nginx config text."""
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _directives_of_block(nginx_code: str, start: int) -> tuple[list[str], bool]:
    """Collect the directives of the block whose opening brace precedes ``start``.

    Walks the characters after the opening brace while counting brace depth,
    so the block is bounded by its braces rather than by line position.
    Returns ``(directives, closed)`` where ``closed`` is True once the
    block's closing brace has been consumed.
    """
    directives: list[str] = []
    pending: list[str] = []
    depth = 1
    for char in nginx_code[start:]:
        if char == "{":
            depth += 1
            pending = []
        elif char == "}":
            depth -= 1
            pending = []
            if depth == 0:
                return directives, True
        elif char == ";":
            if depth == 1:
                directive = "".join(pending + [char]).strip()
                if directive:
                    directives.append(directive)
            pending = []
        elif depth == 1:
            pending.append(char)
    return directives, False


def _location_blocks(nginx_code: str) -> dict[str, list[str]]:
    """Return ``{location prefix: [directives...]}`` found by brace matching."""
    blocks: dict[str, list[str]] = {}
    for match in re.finditer(r"\blocation\s+(\S+)\s*\{", nginx_code):
        prefix = match.group(1)
        directives, closed = _directives_of_block(nginx_code, match.end())
        assert closed, f"location {prefix!r} in app/nginx.conf is never closed"
        assert prefix not in blocks, f"duplicate location {prefix!r} in app/nginx.conf"
        blocks[prefix] = directives
    return blocks


def _server_level_directives(nginx_code: str) -> list[str]:
    """Return the directives that sit directly inside the server block."""
    match = re.search(r"\bserver\s*\{", nginx_code)
    assert match is not None, "app/nginx.conf has no server block"
    directives, closed = _directives_of_block(nginx_code, match.end())
    assert closed, "server block in app/nginx.conf is never closed"
    return directives


def test_issue811_freeform():
    with open(_NGINX_CONF, encoding="utf-8") as fh:
        nginx_text = fh.read()
    code = _strip_nginx_comments(nginx_text)

    # All four locations are found by brace matching — no more, no less.
    blocks = _location_blocks(code)
    assert set(blocks) == set(
        EXPECTED_LOCATION_DIRECTIVES
    ), f"unexpected location blocks: {sorted(blocks)}"

    # AC-2: every other directive of every block is exactly the base-branch
    # one (the only delta anywhere is the no-cache line in location /).
    for prefix, expected in EXPECTED_LOCATION_DIRECTIVES.items():
        assert blocks[prefix] == expected, (
            f"location {prefix!r} directives drifted from the base branch:\n"
            f"  expected: {expected}\n"
            f"  found:    {blocks[prefix]}"
        )

    # AC-1: location / revalidates every response — pages, scripts,
    # stylesheets, images, the try_files index.html fallback and every status
    # (the `always` flag covers error responses too). Requests rewritten in
    # from /app/ land here as well, so they get the same header.
    assert 'add_header Cache-Control "no-cache" always;' in blocks["/"]

    # AC-1/AC-3: the API proxy keeps its base-branch headers and carries no
    # Cache-Control header of its own; neither does the server level, so
    # nothing is inherited into /api/ and its responses stay free of the
    # no-cache header.
    assert not any(
        "Cache-Control" in directive
        for directive in blocks["/api/"]
        if directive.startswith("add_header ")
    )
    assert not any(
        "Cache-Control" in directive
        for directive in _server_level_directives(code)
        if directive.startswith("add_header ")
    )

    # The request-body ceiling is unchanged: one server-level directive, not
    # inside any location block.
    server_directives = _server_level_directives(code)
    assert [d for d in server_directives if d == "client_max_body_size 1m;"] == [
        "client_max_body_size 1m;"
    ]
