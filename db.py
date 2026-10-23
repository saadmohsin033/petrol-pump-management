"""Database utilities for the Petrol Pump Management dashboard."""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()  # Load local .env values when running from VS Code.
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import URL


def get_engine() -> Engine:
    """Create a pooled MySQL connection using environment-based credentials."""
    required = ["DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(
            "Missing environment variables: " + ", ".join(missing)
            + ". Copy .env.example to .env and fill in your Aiven credentials."
        )

    ssl_args = {}
    ca_path = os.getenv("DB_SSL_CA", "").strip()
    if ca_path:
        if not Path(ca_path).is_file():
            raise RuntimeError(f"DB_SSL_CA file was not found: {ca_path}")
        ssl_args = {"ssl": {"ca": ca_path}}
    else:
        # Encrypt the connection. For certificate/hostname verification, set
        # DB_SSL_CA to the CA certificate downloaded from your Aiven console.
        ssl_args = {"ssl": {}}

    url = URL.create(
        drivername="mysql+pymysql",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.environ["DB_NAME"],
        query={"charset": "utf8mb4"},
    )

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5,
        max_overflow=5,
        connect_args=ssl_args,
    )


def test_connection(engine: Engine) -> str:
    with engine.connect() as connection:
        row = connection.execute(text("SELECT DATABASE() AS db, VERSION() AS version")).mappings().one()
    return f"Connected to `{row['db']}` (MySQL {row['version']})."


def read_df(engine: Engine, query: str, params: dict | None = None) -> pd.DataFrame:
    """Read a parameterized SQL query into a DataFrame."""
    with engine.connect() as connection:
        return pd.read_sql_query(text(query), connection, params=params or {})


def get_table_names(engine: Engine) -> list[str]:
    """List tables and views in the selected database."""
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            ORDER BY TABLE_NAME
        """)).scalars().all()
    return list(rows)


def get_columns(engine: Engine, table_name: str) -> list[str]:
    """Return columns for a selected table/view, after checking its name."""
    if table_name not in get_table_names(engine):
        raise ValueError("Unknown table or view.")
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name
            ORDER BY ORDINAL_POSITION
        """), {"table_name": table_name}).scalars().all()
    return list(rows)


def read_table(engine: Engine, table_name: str, limit: int = 500) -> pd.DataFrame:
    """Read a table/view chosen from information_schema (identifier allow-listed)."""
    if table_name not in get_table_names(engine):
        raise ValueError("Unknown table or view.")
    # Identifiers cannot be SQL parameters; quote only a name verified above.
    safe_name = table_name.replace("`", "``")
    return read_df(engine, f"SELECT * FROM `{safe_name}` LIMIT :row_limit", {"row_limit": limit})


def record_sale(
    engine: Engine,
    fuel_id: int,
    employee_id: int,
    quantity: float,
    price_per_litre: float,
    payment_method: str,
    customer_id: int | None = None,
) -> int:
    """
    Insert a sale and its payment atomically.

    The uploaded schema's BEFORE INSERT trigger calculates total_amount and
    deducts stock. We intentionally do not update Fuel.current_stock here.
    """
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")
    if price_per_litre < 0:
        raise ValueError("Price cannot be negative.")
    allowed_methods = {"Cash", "UPI", "Card", "Credit"}
    if payment_method not in allowed_methods:
        raise ValueError("Select a valid payment method.")

    with engine.begin() as connection:
        sale_result = connection.execute(text("""
            INSERT INTO Fuel_Sale
                (fuel_id, employee_id, customer_id, quantity,
                 price_per_litre, total_amount)
            VALUES
                (:fuel_id, :employee_id, :customer_id, :quantity,
                 :price_per_litre, 0)
        """), {
            "fuel_id": fuel_id,
            "employee_id": employee_id,
            "customer_id": customer_id,
            "quantity": quantity,
            "price_per_litre": price_per_litre,
        })
        sale_id = int(sale_result.lastrowid)

        # The sale trigger sets total_amount to quantity * price_per_litre.
        # Read the stored total, then add its payment record in this transaction.
        total = connection.execute(text("""
            SELECT total_amount FROM Fuel_Sale WHERE sale_id = :sale_id
        """), {"sale_id": sale_id}).scalar_one()

        connection.execute(text("""
            INSERT INTO Payment (sale_id, payment_method, amount_paid, payment_status)
            VALUES (:sale_id, :payment_method, :amount_paid, 'Paid')
        """), {
            "sale_id": sale_id,
            "payment_method": payment_method,
            "amount_paid": total,
        })
    return sale_id
