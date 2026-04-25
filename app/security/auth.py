import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.responses import JSONResponse, RedirectResponse

bearer_scheme = HTTPBearer(auto_error=False)
TOKEN_COOKIE_NAME = "access_token"
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 8
PUBLIC_PATHS = {"/health", "/login", "/auth/login"}


def get_configured_credentials() -> tuple[str | None, str | None]:
    return os.getenv("APP_USERNAME"), os.getenv("APP_PASSWORD")


def get_jwt_secret_key() -> str | None:
    return os.getenv("JWT_SECRET_KEY")


def credentials_are_valid(username: str, password: str) -> bool:
    expected_username, expected_password = get_configured_credentials()
    if not expected_username or not expected_password:
        return False
    username_matches = secrets.compare_digest(username, expected_username)
    password_matches = secrets.compare_digest(password, expected_password)
    return username_matches and password_matches


def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(username: str) -> str:
    secret_key = get_jwt_secret_key()
    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY nao configurada")

    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=JWT_EXPIRATION_HOURS)).timestamp()),
    }
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    encoded_header = base64url_encode(json.dumps(header, separators=(",", ":")).encode())
    encoded_payload = base64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    unsigned_token = f"{encoded_header}.{encoded_payload}"
    signature = hmac.new(
        secret_key.encode(),
        unsigned_token.encode(),
        hashlib.sha256,
    ).digest()
    return f"{unsigned_token}.{base64url_encode(signature)}"


def decode_access_token(token: str) -> dict[str, Any]:
    secret_key = get_jwt_secret_key()
    if not secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_SECRET_KEY nao configurada",
        )

    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        unsigned_token = f"{encoded_header}.{encoded_payload}"
        expected_signature = hmac.new(
            secret_key.encode(),
            unsigned_token.encode(),
            hashlib.sha256,
        ).digest()
        provided_signature = base64url_decode(encoded_signature)
        if not hmac.compare_digest(expected_signature, provided_signature):
            raise ValueError("assinatura invalida")

        header = json.loads(base64url_decode(encoded_header))
        if header.get("alg") != JWT_ALGORITHM:
            raise ValueError("algoritmo invalido")

        payload = json.loads(base64url_decode(encoded_payload))
        if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("token expirado")
        return payload
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido ou expirado",
        ) from exc


def get_token_from_request(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token
    return request.cookies.get(TOKEN_COOKIE_NAME)


def verify_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    token = credentials.credentials if credentials else get_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token ausente",
        )
    payload = decode_access_token(token)
    return str(payload["sub"])


def unauthorized_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "Token ausente ou invalido"},
    )


def should_redirect_to_login(path: str) -> bool:
    return path in {"/", "/dashboard", "/docs", "/openapi.json"} or path.startswith("/static/")


async def require_jwt_middleware(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS:
        return await call_next(request)

    token = get_token_from_request(request)
    if token:
        try:
            decode_access_token(token)
            return await call_next(request)
        except HTTPException:
            pass

    if should_redirect_to_login(path):
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return unauthorized_response()
