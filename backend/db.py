import os

import psycopg


def connect_db():
    """Open a connection to the FinTrack database."""
    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=15)