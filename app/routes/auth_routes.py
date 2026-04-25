from fastapi import APIRouter, HTTPException, Response, status

from app.schemas.auth_schema import LoginRequest, LoginResponse
from app.security.auth import (
    JWT_EXPIRATION_HOURS,
    TOKEN_COOKIE_NAME,
    create_access_token,
    credentials_are_valid,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response):
    if not credentials_are_valid(payload.username, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario ou senha invalidos",
        )

    token = create_access_token(payload.username)
    max_age = JWT_EXPIRATION_HOURS * 60 * 60
    response.set_cookie(
        key=TOKEN_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=False,
        samesite="lax",
    )
    return LoginResponse(access_token=token, expires_in=max_age)
