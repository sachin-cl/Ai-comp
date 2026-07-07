"""Password hashing and JWT lifecycle."""
import uuid

import pytest

from app.core.errors import UnauthorizedError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


class TestPasswords:
    def test_hash_and_verify(self):
        hashed = hash_password("s3cret!")
        assert hashed != "s3cret!"
        assert verify_password("s3cret!", hashed)

    def test_wrong_password_rejected(self):
        assert not verify_password("wrong", hash_password("s3cret!"))

    def test_garbage_hash_rejected_not_raised(self):
        assert not verify_password("anything", "not-a-bcrypt-hash")


class TestAccessTokens:
    def test_round_trip(self):
        user_id = uuid.uuid4()
        token, expires_in = create_access_token(user_id, "member")
        assert expires_in > 0
        payload = decode_access_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["role"] == "member"
        assert payload["type"] == "access"

    def test_tampered_token_rejected(self):
        token, _ = create_access_token(uuid.uuid4(), "member")
        with pytest.raises(UnauthorizedError):
            decode_access_token(token[:-2] + "xx")

    def test_wrong_token_type_rejected(self):
        import jwt as pyjwt

        from app.core.config import get_settings

        wrong = pyjwt.encode(
            {"sub": str(uuid.uuid4()), "type": "refresh"},
            get_settings().secret_key,
            algorithm="HS256",
        )
        with pytest.raises(UnauthorizedError, match="Wrong token type"):
            decode_access_token(wrong)


class TestRefreshTokens:
    def test_generated_tokens_unique(self):
        assert generate_refresh_token() != generate_refresh_token()

    def test_hash_deterministic(self):
        token = generate_refresh_token()
        assert hash_refresh_token(token) == hash_refresh_token(token)
        assert len(hash_refresh_token(token)) == 64  # sha256 hex
