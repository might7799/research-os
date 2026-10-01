import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import JWT_ACCESS_TOKEN_TTL_SECONDS, JWT_ALGORITHM, JWT_SECRET

security = HTTPBearer()


def create_token(subject: str) -> str:
    issued_at = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": subject,
            "type": "access",
            "iat": issued_at,
            "exp": issued_at + timedelta(seconds=JWT_ACCESS_TOKEN_TTL_SECONDS),
            "jti": secrets.token_urlsafe(16),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_token_value(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "jti", "sub", "type"]},
        )
        if payload["type"] != "access" or not isinstance(payload["sub"], str):
            raise ValueError("Invalid access token")
        return payload["sub"]
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def decode_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    decode_token_value(credentials.credentials)
    return credentials.credentials
