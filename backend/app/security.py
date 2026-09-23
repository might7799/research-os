import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import JWT_ALGORITHM, JWT_SECRET

security = HTTPBearer()


def create_token(subject: str) -> str:
    return jwt.encode({"sub": subject, "type": "access"}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token_value(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload["sub"]
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def decode_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    return decode_token_value(credentials.credentials)
