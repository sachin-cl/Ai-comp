"""Auth API: register, login, me, refresh rotation, logout, error envelope."""
from tests.conftest import register_and_login

REGISTER = {"email": "user@example.com", "password": "password123", "full_name": "User"}


class TestRegister:
    async def test_register_created(self, client):
        res = await client.post("/api/v1/auth/register", json=REGISTER)
        assert res.status_code == 201
        body = res.json()
        assert body["email"] == "user@example.com"
        assert body["role"] == "member"
        assert "password" not in res.text

    async def test_duplicate_email_conflict(self, client):
        await client.post("/api/v1/auth/register", json=REGISTER)
        res = await client.post("/api/v1/auth/register", json=REGISTER)
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "EMAIL_TAKEN"

    async def test_invalid_email_422_envelope(self, client):
        res = await client.post(
            "/api/v1/auth/register",
            json={**REGISTER, "email": "not-an-email"},
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"


class TestLogin:
    async def test_login_ok(self, client):
        await client.post("/api/v1/auth/register", json=REGISTER)
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER["email"], "password": REGISTER["password"]},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["access_token"] and body["refresh_token"]
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0

    async def test_wrong_password_401(self, client):
        await client.post("/api/v1/auth/register", json=REGISTER)
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER["email"], "password": "wrong-password"},
        )
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"

    async def test_unknown_user_401(self, client):
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "password123"},
        )
        assert res.status_code == 401


class TestMe:
    async def test_me_with_token(self, client, auth_headers):
        res = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["email"] == "owner@example.com"

    async def test_me_without_token_401(self, client):
        res = await client.get("/api/v1/auth/me")
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "UNAUTHORIZED"

    async def test_me_with_garbage_token_401(self, client):
        res = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}
        )
        assert res.status_code == 401


class TestRefresh:
    async def test_rotation(self, client):
        await client.post("/api/v1/auth/register", json=REGISTER)
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER["email"], "password": REGISTER["password"]},
        )
        old_refresh = login.json()["refresh_token"]

        res = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert res.status_code == 200
        new_refresh = res.json()["refresh_token"]
        assert new_refresh != old_refresh

        # Replay of the rotated-out token is rejected.
        replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"

    async def test_logout_revokes_refresh(self, client):
        await client.post("/api/v1/auth/register", json=REGISTER)
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER["email"], "password": REGISTER["password"]},
        )
        tokens = login.json()
        res = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert res.status_code == 204
        replay = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert replay.status_code == 401


async def test_register_and_login_helper(client):
    headers = await register_and_login(client, "helper@example.com")
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
