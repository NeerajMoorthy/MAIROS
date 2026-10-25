"""Optional authentication: Better Auth JWTs verified against a published key set.

Tokens here are really signed (Ed25519, the Better Auth JWT plugin's default)
and really verified — only the HTTP fetch of the key set is replaced, so the
suite stays offline. What is asserted is the isolation boundary: with auth on,
nothing works without a valid token, and nobody can see, list, query, modify or
delete a project they do not own.
"""

from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ISSUER = "https://mairos.example.com"


@pytest.fixture()
def signing_keys():
    private = Ed25519PrivateKey.generate()
    public_jwk = json.loads(jwt.algorithms.OKPAlgorithm.to_jwk(private.public_key()))
    public_jwk.update({"kid": "key-1", "alg": "EdDSA", "use": "sig"})
    return private, {"keys": [public_jwk]}


@pytest.fixture()
def auth_on(monkeypatch, signing_keys):
    from app import auth
    from app.config import settings

    _private, jwks = signing_keys

    async def fake_fetch(url):
        assert url == "https://mairos.example.com/api/auth/jwks"
        return jwks

    monkeypatch.setattr(auth, "fetch_jwks", fake_fetch)
    monkeypatch.setattr(settings, "auth_jwks_url", f"{ISSUER}/api/auth/jwks")
    monkeypatch.setattr(settings, "auth_issuer", ISSUER)
    monkeypatch.setattr(settings, "auth_audience", ISSUER)
    auth.jwks_cache.clear()
    yield
    auth.jwks_cache.clear()


def token(private, sub: str, *, exp_in: int = 900, aud: str = ISSUER, iss: str = ISSUER, kid: str = "key-1") -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": sub, "email": f"{sub}@example.com", "iat": now, "exp": now + exp_in, "aud": aud, "iss": iss},
        private,
        algorithm="EdDSA",
        headers={"kid": kid},
    )


def headers_for(private, sub: str) -> dict:
    return {"Authorization": f"Bearer {token(private, sub)}"}


class TestLocalMode:
    def test_no_token_needed_and_everything_visible(self, client):
        created = client.post("/api/projects", json={"name": "Local"})
        assert created.status_code == 201
        assert [p["name"] for p in client.get("/api/projects").json()] == ["Local"]
        assert client.get("/api/health").json()["auth"] == "local single-user mode"


class TestTokenVerification:
    def test_missing_token_is_401_with_a_bearer_challenge(self, client, auth_on):
        response = client.get("/api/projects")
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_valid_token_is_accepted(self, client, auth_on, signing_keys):
        private, _ = signing_keys
        assert client.get("/api/projects", headers=headers_for(private, "alice")).status_code == 200

    @pytest.mark.parametrize(
        "kwargs",
        [{"exp_in": -120}, {"aud": "https://evil.example.com"}, {"iss": "https://evil.example.com"}, {"kid": "unknown"}],
        ids=["expired", "wrong-audience", "wrong-issuer", "unknown-key"],
    )
    def test_bad_tokens_are_refused(self, client, auth_on, signing_keys, kwargs):
        private, _ = signing_keys
        bad = token(private, "alice", **kwargs)
        assert client.get("/api/projects", headers={"Authorization": f"Bearer {bad}"}).status_code == 401

    def test_a_token_signed_by_another_key_is_refused(self, client, auth_on):
        forged = token(Ed25519PrivateKey.generate(), "alice")
        assert client.get("/api/projects", headers={"Authorization": f"Bearer {forged}"}).status_code == 401

    def test_symmetric_algorithms_are_not_accepted(self, client, auth_on):
        # The classic confusion attack: sign HS256 with a public value as the secret.
        now = int(time.time())
        forged = jwt.encode(
            {"sub": "alice", "exp": now + 60, "aud": ISSUER, "iss": ISSUER},
            "a" * 32,
            algorithm="HS256",
            headers={"kid": "key-1"},
        )
        assert client.get("/api/projects", headers={"Authorization": f"Bearer {forged}"}).status_code == 401

    def test_health_stays_open_and_reveals_no_counts(self, client, auth_on):
        body = client.get("/api/health").json()
        assert body["auth"] == "enabled"
        assert "projects" not in body


class TestIsolation:
    def _project(self, client, private, owner: str) -> str:
        return client.post("/api/projects", json={"name": f"{owner}'s"}, headers=headers_for(private, owner)).json()["id"]

    def test_users_only_list_their_own_projects(self, client, auth_on, signing_keys):
        private, _ = signing_keys
        self._project(client, private, "alice")
        self._project(client, private, "bob")
        names = [p["name"] for p in client.get("/api/projects", headers=headers_for(private, "alice")).json()]
        assert names == ["alice's"]

    def test_another_users_project_is_indistinguishable_from_a_missing_one(self, client, auth_on, signing_keys):
        private, _ = signing_keys
        project_id = self._project(client, private, "alice")
        bob = headers_for(private, "bob")

        for method, path, body in [
            ("GET", f"/api/projects/{project_id}", None),
            ("GET", f"/api/projects/{project_id}/stats", None),
            ("GET", f"/api/projects/{project_id}/graph", None),
            ("GET", f"/api/projects/{project_id}/patents", None),
            ("POST", f"/api/projects/{project_id}/query", {"question": "x"}),
            ("POST", f"/api/projects/{project_id}/tasks", {"question": "x"}),
            ("POST", f"/api/projects/{project_id}/patents", {"title": "x", "text": "y"}),
            ("DELETE", f"/api/projects/{project_id}", None),
        ]:
            response = client.request(method, path, json=body, headers=bob)
            assert response.status_code == 404, (method, path, response.status_code)

        # Still there for its owner.
        assert client.get(f"/api/projects/{project_id}", headers=headers_for(private, "alice")).status_code == 200

    def test_tasks_are_scoped_through_their_project(self, client, auth_on, signing_keys):
        private, _ = signing_keys
        alice = headers_for(private, "alice")
        project_id = self._project(client, private, "alice")
        task_id = client.post(
            f"/api/projects/{project_id}/tasks", json={"question": "what is here?", "flow": "answer"}, headers=alice
        ).json()["id"]

        bob = headers_for(private, "bob")
        assert client.get(f"/api/tasks/{task_id}", headers=bob).status_code == 404
        assert client.get(f"/api/tasks/{task_id}/events", headers=bob).status_code == 404
        assert client.get("/api/tasks", headers=bob).json() == []
        assert [t["id"] for t in client.get("/api/tasks", headers=alice).json()] == [task_id]

    def test_projects_from_before_auth_are_not_exposed_to_anyone(self, client, auth_on, signing_keys):
        from app.store import metadata_store

        legacy = metadata_store.create_project("Pre-auth project")  # owner_id == ""
        private, _ = signing_keys
        assert client.get(f"/api/projects/{legacy.id}", headers=headers_for(private, "alice")).status_code == 404


class TestRateLimitKeying:
    def test_signed_in_users_get_separate_budgets(self, signing_keys):
        from starlette.requests import Request

        from app.middleware import RateLimitMiddleware

        private, _ = signing_keys
        limiter = RateLimitMiddleware(app=None)

        def request_with(headers: dict) -> Request:
            raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
            return Request({"type": "http", "headers": raw, "client": ("10.0.0.1", 1), "method": "GET", "path": "/"})

        assert limiter._client(request_with(headers_for(private, "alice"))) == "user:alice"
        assert limiter._client(request_with(headers_for(private, "bob"))) == "user:bob"
        assert limiter._client(request_with({})) == "10.0.0.1"
        assert limiter._client(request_with({"Authorization": "Bearer not-a-jwt"})) == "10.0.0.1"
