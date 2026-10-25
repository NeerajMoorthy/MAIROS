"""Optional authentication: Better Auth sessions, verified as signed JWTs.

**Off by default.** With ``AUTH_JWKS_URL`` unset MAIROS is the single-user,
local-first tool it has always been: no login, every project visible, and every
existing test runs unchanged. Turning auth on is configuration, not a code path
anyone has to remember to switch.

**How it works when on.** Sign-in happens in the Next.js frontend through
Better Auth, whose JWT plugin issues a short-lived token signed with a key
published at ``/api/auth/jwks``. The browser sends that token as
``Authorization: Bearer …``; this module verifies the signature against the
published key set, plus expiry, issuer and audience. The API never sees a
password or a session cookie, and it needs no database access to Better Auth's
tables — the key set is the only shared secret, and it is public.

**What it protects.** One dependency, :func:`authorize`, runs before every API
route. It authenticates the caller and, whenever the route names a
``project_id`` or a ``task_id``, checks that the project belongs to them.
Projects, documents, chunks, graphs, patents, tasks and evaluations are all
scoped by project, so that single check is the whole isolation boundary — no
router has to repeat it. A project the caller does not own answers 404, not
403, so its existence is not disclosed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.config import settings
from app.store import metadata_store

LOCAL_USER_ID = ""

# Signature algorithms Better Auth's JWT plugin can be configured to use.
# Symmetric HS* is deliberately absent: a key published in a JWKS must never be
# usable to *sign*.
ALLOWED_ALGORITHMS = ["EdDSA", "ES256", "ES512", "RS256", "PS256"]


@dataclass(frozen=True)
class CurrentUser:
    """Who is calling. ``id`` is empty in local single-user mode."""

    id: str
    email: str = ""
    name: str = ""

    @property
    def is_local(self) -> bool:
        return self.id == LOCAL_USER_ID


LOCAL_USER = CurrentUser(id=LOCAL_USER_ID)


# ---------------------------------------------------------------------------
# Key set
# ---------------------------------------------------------------------------
async def fetch_jwks(url: str) -> dict:
    """Download the published key set. Replaced in tests."""
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


class _JWKSCache:
    """Keys by ``kid``, refreshed on expiry or when an unknown ``kid`` arrives.

    The unknown-``kid`` refresh is what makes key rotation work without a
    restart; it is rate-limited so a stream of forged ``kid`` values cannot turn
    the API into a JWKS-fetching amplifier.
    """

    MIN_REFRESH_SECONDS = 30.0

    def __init__(self) -> None:
        self._keys: dict[str, object] = {}
        self._fetched_at = 0.0

    def clear(self) -> None:
        self._keys = {}
        self._fetched_at = 0.0

    async def _refresh(self) -> None:
        import jwt

        payload = await fetch_jwks(settings.auth_jwks_url)
        keys: dict[str, object] = {}
        for entry in payload.get("keys", []):
            try:
                keys[str(entry.get("kid", ""))] = jwt.PyJWK.from_dict(entry)
            except Exception:
                continue  # an unsupported key type must not take the others down
        self._keys = keys
        self._fetched_at = time.monotonic()

    async def key_for(self, kid: str):
        age = time.monotonic() - self._fetched_at
        if not self._keys or age > settings.auth_jwks_cache_seconds:
            await self._refresh()
        elif kid not in self._keys and age > self.MIN_REFRESH_SECONDS:
            await self._refresh()
        return self._keys.get(kid)


jwks_cache = _JWKSCache()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


async def verify_token(token: str) -> CurrentUser:
    """Verify a Better Auth JWT and return its user, or raise a 401."""
    import jwt

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise _unauthorized("The sign-in token is malformed. Sign in again.") from None

    try:
        key = await jwks_cache.key_for(str(header.get("kid", "")))
    except Exception as exc:
        # The key server being unreachable is an outage, not the caller's fault.
        raise HTTPException(
            status_code=503,
            detail="Sign-in could not be verified because the key server is unreachable. Try again shortly.",
        ) from exc
    if key is None:
        raise _unauthorized("The sign-in token was signed with an unknown key. Sign in again.")

    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=ALLOWED_ALGORITHMS,
            audience=settings.auth_audience or None,
            issuer=settings.auth_issuer or None,
            options={
                "require": ["exp", "sub"],
                "verify_aud": bool(settings.auth_audience),
            },
            leeway=30,
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Your session token has expired. Sign in again.") from None
    except jwt.PyJWTError:
        raise _unauthorized("The sign-in token could not be verified. Sign in again.") from None

    subject = str(claims.get("sub") or claims.get("id") or "").strip()
    if not subject:
        raise _unauthorized("The sign-in token names no user. Sign in again.")
    return CurrentUser(
        id=subject,
        email=str(claims.get("email") or ""),
        name=str(claims.get("name") or ""),
    )


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------
def can_access(user: CurrentUser, project) -> bool:
    """Whether *user* may see *project*. Always true in local mode."""
    if not settings.auth_enabled:
        return True
    return bool(project.owner_id) and project.owner_id == user.id


def owner_filter(user: CurrentUser) -> str | None:
    """The ``owner_id`` to list by — ``None`` (everything) in local mode."""
    return user.id if settings.auth_enabled else None


def visible_project_ids(user: CurrentUser) -> set[str] | None:
    owner = owner_filter(user)
    if owner is None:
        return None
    return {project.id for project in metadata_store.list_projects(owner_id=owner)}


async def authorize(request: Request) -> CurrentUser:
    """Authenticate the caller and enforce project ownership for this route.

    Installed on every API router, and also usable as a parameter dependency
    (``user = Depends(authorize)``) — FastAPI caches it per request, so it runs
    once either way.
    """
    if not settings.auth_enabled:
        user = LOCAL_USER
    else:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise _unauthorized("Sign in to use MAIROS.")
        user = await verify_token(token.strip())

    request.state.user = user

    project_id = request.path_params.get("project_id")
    task_id = request.path_params.get("task_id")
    if task_id and not project_id:
        task = metadata_store.get_task(task_id)
        project_id = task.project_id if task else None

    if project_id:
        project = metadata_store.get_project(project_id)
        # Missing and not-yours read the same, so ids cannot be probed.
        if project is not None and not can_access(user, project):
            raise HTTPException(
                status_code=404,
                detail="Task not found" if task_id and "project_id" not in request.path_params
                else "Project not found",
            )
    return user


__all__ = [
    "ALLOWED_ALGORITHMS",
    "LOCAL_USER",
    "CurrentUser",
    "authorize",
    "can_access",
    "fetch_jwks",
    "jwks_cache",
    "owner_filter",
    "verify_token",
    "visible_project_ids",
]
