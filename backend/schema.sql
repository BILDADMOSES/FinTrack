CREATE TABLE IF NOT EXISTS analysts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text NOT NULL UNIQUE,
    password_hash text NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolios (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analyst_id bigint NOT NULL REFERENCES analysts(id),
    name text NOT NULL,
    client_name text NOT NULL,
    base_currency text NOT NULL CHECK (base_currency IN ('KES', 'USD')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transactions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    portfolio_id bigint NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    instrument text NOT NULL,
    type text NOT NULL CHECK (type IN ('BUY', 'SELL')),
    quantity numeric NOT NULL CHECK (quantity > 0),
    unit_price numeric NOT NULL CHECK (unit_price > 0),
    trade_date date NOT NULL
);