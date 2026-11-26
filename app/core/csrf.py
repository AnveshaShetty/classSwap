import hmac
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status


CSRF_COOKIE_NAME = "__Host-classswap_csrf"


def _same_origin(candidate: str, request: Request) -> bool:
    try:
        parsed = urlsplit(candidate)
        expected = urlsplit(str(request.base_url))
        return (
            parsed.scheme == expected.scheme
            and parsed.netloc == expected.netloc
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


async def require_csrf(request: Request) -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    submitted_token = request.headers.get("X-CSRF-Token", "")
    if not submitted_token and request.headers.get("content-type", "").startswith(
        ("application/x-www-form-urlencoded", "multipart/form-data")
    ):
        form = await request.form()
        submitted_token = str(form.get("csrf_token", ""))

    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    valid_origin = _same_origin(origin, request) if origin else bool(
        referer and _same_origin(referer, request)
    )
    if (
        not cookie_token
        or not submitted_token
        or not hmac.compare_digest(cookie_token, submitted_token)
        or not valid_origin
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This request could not be verified. Reload the page and try again.",
        )
