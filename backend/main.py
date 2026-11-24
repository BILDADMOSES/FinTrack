from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
import os
from datetime import datetime, timedelta, timezone

import jwt

from backend.db import connect_db

app = FastAPI(title = "Fintrack API")

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

password_hasher = PasswordHash.recommended()


class RegistrationRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)

class RegistrationResponse(BaseModel):
    id: int
    username: str

@app.post(
    "/api/auth/register",
    status_code=201,
    response_model=RegistrationResponse,
    responses={409: {"description": "Username already exists"}},
)

def register_analyst(details: RegistrationRequest):
    password_hash = password_hasher.hash(details.password)

    with connect_db() as connection:
        analyst = connection.execute(
            """
            INSERT INTO analysts (username, password_hash)
            VALUES (%s, %s)
            ON CONFLICT (username) DO NOTHING
            RETURNING id, username
            """,
            (details.username, password_hash),
        ).fetchone()

    if analyst is None:
        raise HTTPException(status_code=409, detail="Username already exists")

    return {"id": analyst[0], "username": analyst[1]}

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.post("/api/auth/login", response_model=LoginResponse)
def login_analyst(details: RegistrationRequest):
    with connect_db() as connection:
        analyst = connection.execute(
            "SELECT id, password_hash FROM analysts WHERE username = %s",
            (details.username,),
        ).fetchone()

    if analyst is None or not password_hasher.verify(details.password, analyst[1]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    access_token = jwt.encode(
        {"sub": str(analyst[0]), "exp": expires_at},
        os.environ["FINTRACK_JWT_SECRET"],
        algorithm="HS256",
    )
    return LoginResponse(access_token=access_token)

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_analyst_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> int:
    unauthorized = HTTPException(
        status_code=401,
        detail="A valid access token is required",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    try:
        claims = jwt.decode(
            credentials.credentials,
            os.environ["FINTRACK_JWT_SECRET"],
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
        return int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized from None


@app.get("/api/auth/me")
def get_current_analyst(analyst_id: int = Depends(get_current_analyst_id)):
    return {"id": analyst_id}