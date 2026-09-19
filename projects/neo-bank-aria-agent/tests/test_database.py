from __future__ import annotations

import sqlite3

from database import authenticate_by_name, get_customer, get_transactions, init_database


def test_database_seeding_is_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    init_database(conn)
    init_database(conn)

    assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 15


def test_workshop_identity_can_sign_in() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_database(conn)

    customer = authenticate_by_name(conn, "alex mercer")

    assert customer is not None
    assert customer["user_id"] == "USR-0042"
    assert customer["tier"] == "Standard"


def test_baseline_exposes_other_accounts_for_red_team_exercise() -> None:
    """Document, rather than fix, the intentional broken object authorization."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_database(conn)

    other_customer = get_customer(conn, "USR-PP-001")
    other_transactions = get_transactions(conn, "USR-PP-001")

    assert other_customer is not None
    assert other_customer["name"] == "Adrian Cross"
    assert len(other_transactions) == 4
