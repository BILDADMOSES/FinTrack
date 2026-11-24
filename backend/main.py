from pathlib import Path
from fastapi.responses import FileResponse
from datetime import date
from decimal import Decimal
from psycopg.rows import dict_row
from typing import Literal
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from pwdlib import PasswordHash

from datetime import datetime, timedelta, timezone
import os
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

class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"\S")
    client_name: str = Field(min_length=1, max_length=100, pattern=r"\S")
    base_currency: Literal["KES", "USD"]


class PortfolioResponse(PortfolioCreate):
    id: int
    created_at: datetime


@app.post("/api/portfolios", status_code=201, response_model=PortfolioResponse)
def create_portfolio(
    details: PortfolioCreate,
    analyst_id: int = Depends(get_current_analyst_id),
):
    with connect_db() as connection:
        portfolio = connection.execute(
            """
            INSERT INTO portfolios (analyst_id, name, client_name, base_currency)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, client_name, base_currency, created_at
            """,
            (
                analyst_id,
                details.name.strip(),
                details.client_name.strip(),
                details.base_currency,
            ),
        ).fetchone()

    return PortfolioResponse(
        id=portfolio[0],
        name=portfolio[1],
        client_name=portfolio[2],
        base_currency=portfolio[3],
        created_at=portfolio[4],
    )

@app.get("/api/portfolios", response_model=list[PortfolioResponse])
def list_portfolios(analyst_id: int = Depends(get_current_analyst_id)):
    with connect_db() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, name, client_name, base_currency, created_at
                FROM portfolios
                WHERE analyst_id = %s
                ORDER BY id
                """,
                (analyst_id,),
            )
            return cursor.fetchall()

@app.get("/api/portfolios/{portfolio_id}", response_model=PortfolioResponse)
def get_portfolio(
    portfolio_id: int,
    analyst_id: int = Depends(get_current_analyst_id),
):
    with connect_db() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, name, client_name, base_currency, created_at
                FROM portfolios
                WHERE id = %s AND analyst_id = %s
                """,
                (portfolio_id, analyst_id),
            )
            portfolio = cursor.fetchone()

    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    return portfolio

@app.put("/api/portfolios/{portfolio_id}", response_model=PortfolioResponse)
def update_portfolio(
    portfolio_id: int,
    details: PortfolioCreate,
    analyst_id: int = Depends(get_current_analyst_id),
):
    with connect_db() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                UPDATE portfolios
                SET name = %s, client_name = %s, base_currency = %s
                WHERE id = %s AND analyst_id = %s
                RETURNING id, name, client_name, base_currency, created_at
                """,
                (
                    details.name.strip(),
                    details.client_name.strip(),
                    details.base_currency,
                    portfolio_id,
                    analyst_id,
                ),
            )
            portfolio = cursor.fetchone()

    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    return portfolio

@app.delete("/api/portfolios/{portfolio_id}", status_code=204)
def delete_portfolio(
    portfolio_id: int,
    analyst_id: int = Depends(get_current_analyst_id),
):
    with connect_db() as connection:
        deleted_portfolio = connection.execute(
            """
            DELETE FROM portfolios
            WHERE id = %s AND analyst_id = %s
            RETURNING id
            """,
            (portfolio_id, analyst_id),
        ).fetchone()

    if deleted_portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

@app.get("/api/portfolios/{portfolio_id}/transactions")
def list_transactions(
    portfolio_id: int,
    analyst_id: int = Depends(get_current_analyst_id),
):
    get_portfolio(portfolio_id, analyst_id)

    with connect_db() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, instrument, type, quantity, unit_price, trade_date
                FROM transactions
                WHERE portfolio_id = %s
                ORDER BY trade_date DESC, id DESC
                """,
                (portfolio_id,),
            )
            return cursor.fetchall()

class TransactionCreate(BaseModel):
    instrument: str = Field(min_length=1, max_length=30, pattern=r"\S")
    type: Literal["BUY", "SELL"]
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    unit_price: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    trade_date: date

def check_trade_history(connection, portfolio_id: int, instrument: str):
    lowest_balance = connection.execute(
        """
        SELECT MIN(balance)
        FROM (
            SELECT SUM(
                CASE WHEN type = 'BUY' THEN quantity ELSE -quantity END
            ) OVER (ORDER BY trade_date, id) AS balance
            FROM transactions
            WHERE portfolio_id = %s AND instrument = %s
        ) AS trade_history
        """,
        (portfolio_id, instrument),
    ).fetchone()[0]

    if lowest_balance is not None and lowest_balance < 0:
        raise HTTPException(
            status_code=409,
            detail="This change would leave the portfolio with negative holdings",
        )

@app.post("/api/portfolios/{portfolio_id}/transactions", status_code=201)
def create_transaction(
    portfolio_id: int,
    details: TransactionCreate,
    analyst_id: int = Depends(get_current_analyst_id),
):
    instrument = details.instrument.strip().upper()

    with connect_db() as connection:
        portfolio = connection.execute(
            """
            SELECT id FROM portfolios
            WHERE id = %s AND analyst_id = %s
            FOR UPDATE
            """,
            (portfolio_id, analyst_id),
        ).fetchone()

        if portfolio is None:
            raise HTTPException(status_code=404, detail="Portfolio not found")

        trade = connection.execute(
            """
            INSERT INTO transactions
                (portfolio_id, instrument, type, quantity, unit_price, trade_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                portfolio_id, instrument, details.type,
                details.quantity, details.unit_price, details.trade_date,
            ),
        ).fetchone()

        check_trade_history(connection, portfolio_id, instrument)

    return {"id": trade[0]}

@app.get("/api/portfolios/{portfolio_id}/summary")
def get_portfolio_summary(
    portfolio_id: int,
    analyst_id: int = Depends(get_current_analyst_id),
):
    portfolio = get_portfolio(portfolio_id, analyst_id)
    trades = reversed(list_transactions(portfolio_id, analyst_id))
    holdings = {}

    for trade in trades:
        instrument = trade["instrument"]
        holding = holdings.setdefault(
            instrument,
            {"quantity": Decimal("0"), "cost": Decimal("0")},
        )
        quantity = trade["quantity"]
        price = trade["unit_price"]

        if trade["type"] == "BUY":
            holding["quantity"] += quantity
            holding["cost"] += quantity * price
        else:
            remaining = holding["quantity"] - quantity
            holding["cost"] *= remaining / holding["quantity"]
            holding["quantity"] = remaining

        holding["latest_trade_price"] = price

    return {
        "base_currency": portfolio["base_currency"],
        "holdings": [
            {
                "instrument": instrument,
                "net_quantity": holding["quantity"],
                "average_cost": (holding["cost"] / holding["quantity"]).quantize(
                    Decimal("0.01")
                ),
                "total_invested": holding["cost"].quantize(Decimal("0.01")),
                "total_value": (
                    holding["quantity"] * holding["latest_trade_price"]
                ).quantize(Decimal("0.01")),
            }
            for instrument, holding in holdings.items()
            if holding["quantity"] > 0
        ],
    }

@app.delete("/api/transactions/{transaction_id}", status_code=204)
def delete_transaction(
    transaction_id: int,
    analyst_id: int = Depends(get_current_analyst_id),
):
    with connect_db() as connection:
        portfolio = connection.execute(
            """
            SELECT p.id
            FROM portfolios AS p
            JOIN transactions AS t ON t.portfolio_id = p.id
            WHERE t.id = %s AND p.analyst_id = %s
            FOR UPDATE OF p
            """,
            (transaction_id, analyst_id),
        ).fetchone()

        if portfolio is None:
            raise HTTPException(status_code=404, detail="Transaction not found")

        deleted = connection.execute(
            """
            DELETE FROM transactions
            WHERE id = %s AND portfolio_id = %s
            RETURNING instrument
            """,
            (transaction_id, portfolio[0]),
        ).fetchone()

        if deleted is None:
            raise HTTPException(status_code=404, detail="Transaction not found")

        check_trade_history(connection, portfolio[0], deleted[0])

@app.get("/", include_in_schema=False)
def home():
    return FileResponse(Path(__file__).resolve().parent / "index.html")