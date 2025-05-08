"""
Extension functions for the Fontana database module.

This module provides additional database functions needed for the CLI integration.
"""

from typing import Optional

from fontana.core.db import db
from fontana.core.models.utxo import UTXO


def fetch_utxo(txid: str, output_index: int) -> Optional[UTXO]:
    """
    Fetch a specific UTXO by txid and output_index.

    Args:
        txid: Transaction ID
        output_index: Output index

    Returns:
        UTXO: The UTXO if found, None otherwise
    """
    with db.get_connection() as conn:
        conn.row_factory = db.dict_from_row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM utxos " "WHERE txid = ? AND output_index = ?",
            (txid, output_index),
        )
        row = cur.fetchone()
        if row:
            return UTXO.from_sql_row(row)
        return None
