import sqlite3
import os
from pathlib import Path
import json

from fontana.core.models.utxo import UTXO
from fontana.core.models.transaction import SignedTransaction
from fontana.core.models.block import Block
from fontana.core.models.vault import VaultDeposit, VaultWithdrawal
from fontana.core.models.receipt import ReceiptProof

DB_PATH = Path.home() / ".fontana" / "ledger.db"
os.makedirs(DB_PATH.parent, exist_ok=True)


def get_connection():
    return sqlite3.connect(DB_PATH)


def dict_from_row(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


# ───────────────────────────────
# 🏗️  Initialization
# ───────────────────────────────

def init_db():
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            "CREATE TABLE IF NOT EXISTS utxos ("
            "txid TEXT, "
            "output_index INTEGER, "
            "recipient TEXT, "
            "amount REAL, "
            "status TEXT, "
            "PRIMARY KEY (txid, output_index)"
            ")"
        )

        cur.execute(
            "CREATE TABLE IF NOT EXISTS transactions ("
            "txid TEXT PRIMARY KEY, "
            "sender_address TEXT, "
            "inputs_json TEXT, "
            "outputs_json TEXT, "
            "fee REAL, "
            "payload_hash TEXT, "
            "timestamp INTEGER, "
            "signature TEXT"
            ")"
        )

        cur.execute(
            "CREATE TABLE IF NOT EXISTS blocks ("
            "height INTEGER PRIMARY KEY, "
            "header_json TEXT, "
            "txs_json TEXT, "
            "committed INTEGER DEFAULT 0, "
            "blob_ref TEXT"
            ")"
        )

        cur.execute(
            "CREATE TABLE IF NOT EXISTS vault_deposits ("
            "depositor_address TEXT, "
            "rollup_wallet_address TEXT, "
            "vault_address TEXT, "
            "tx_hash TEXT, "
            "amount REAL, "
            "timestamp INTEGER, "
            "height INTEGER, "
            "processed INTEGER DEFAULT 0, "
            "PRIMARY KEY (tx_hash, rollup_wallet_address)"
            ")"
        )

        cur.execute(
            "CREATE TABLE IF NOT EXISTS vault_withdrawals ("
            "recipient_rollup_address TEXT, "
            "recipient_celestia_address TEXT, "
            "vault_address TEXT, "
            "amount REAL, "
            "timestamp INTEGER, "
            "related_utxos_json TEXT, "
            "tx_hash TEXT PRIMARY KEY, "
            "processed_by TEXT"
            ")"
        )

        cur.execute(
            "CREATE TABLE IF NOT EXISTS receipts ("
            "receipt_id TEXT PRIMARY KEY, "
            "txid TEXT, "
            "block_height INTEGER, "
            "timestamp INTEGER, "
            "provider TEXT, "
            "amount REAL, "
            "endpoint TEXT, "
            "full_json TEXT"
            ")"
        )

        conn.commit()


# ───────────────────────────────
# 💰 UTXO Operations
# ───────────────────────────────

def insert_utxo(utxo: UTXO):
    row = utxo.to_sql_row()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO utxos (txid, output_index, recipient, amount, status) "
            "VALUES (:txid, :output_index, :recipient, :amount, :status)",
            row
        )
        conn.commit()


def fetch_unspent_utxos(address: str) -> list[UTXO]:
    with get_connection() as conn:
        conn.row_factory = dict_from_row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM utxos "
            "WHERE recipient = :recipient AND status = 'unspent'",
            {"recipient": address}
        )
        return [UTXO.from_sql_row(row) for row in cur.fetchall()]


def mark_utxo_spent(txid: str, output_index: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE utxos SET status = 'spent' "
            "WHERE txid = :txid AND output_index = :output_index",
            {"txid": txid, "output_index": output_index}
        )
        conn.commit()


# ───────────────────────────────
# 🧾 Transaction Ledger
# ───────────────────────────────

def insert_transaction(tx: SignedTransaction):
    row = tx.to_sql_row()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO transactions ("
            "txid, sender_address, inputs_json, outputs_json, "
            "fee, payload_hash, timestamp, signature"
            ") VALUES ("
            ":txid, :sender_address, :inputs_json, :outputs_json, "
            ":fee, :payload_hash, :timestamp, :signature"
            ")",
            row
        )
        conn.commit()


# ───────────────────────────────
# 📦 Block Operations
# ───────────────────────────────

def insert_block(block: Block):
    row = block.to_sql_row()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO blocks (height, header_json, txs_json, committed, blob_ref) "
            "VALUES (:height, :header_json, :txs_json, :committed, :blob_ref)",
            row
        )
        conn.commit()


def fetch_uncommitted_blocks() -> list[Block]:
    with get_connection() as conn:
        conn.row_factory = dict_from_row
        cur = conn.cursor()
        cur.execute("SELECT * FROM blocks WHERE committed = 0")
        return [Block.from_sql_row(row) for row in cur.fetchall()]


def mark_block_committed(height: int, blob_ref: str):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE blocks SET committed = 1, blob_ref = :blob_ref "
            "WHERE height = :height",
            {"height": height, "blob_ref": blob_ref}
        )
        conn.commit()


def get_block_by_height(height: int) -> Block | None:
    with get_connection() as conn:
        conn.row_factory = dict_from_row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM blocks WHERE height = :height",
            {"height": height}
        )
        row = cur.fetchone()
        return Block.from_sql_row(row) if row else None


# ───────────────────────────────
# 🏦 Vault Deposits
# ───────────────────────────────

def insert_vault_deposit(deposit: VaultDeposit):
    row = deposit.to_sql_row()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO vault_deposits ("
            "depositor_address, rollup_wallet_address, vault_address, "
            "tx_hash, amount, timestamp, height, processed"
            ") VALUES ("
            ":depositor_address, :rollup_wallet_address, :vault_address, "
            ":tx_hash, :amount, :timestamp, :height, :processed"
            ")",
            row
        )
        conn.commit()


def fetch_unprocessed_deposits() -> list[VaultDeposit]:
    with get_connection() as conn:
        conn.row_factory = dict_from_row
        cur = conn.cursor()
        cur.execute("SELECT * FROM vault_deposits WHERE processed = 0")
        return [VaultDeposit.from_sql_row(row) for row in cur.fetchall()]


def mark_deposit_processed(tx_hash: str, rollup_wallet_address: str):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE vault_deposits SET processed = 1 "
            "WHERE tx_hash = :tx_hash AND rollup_wallet_address = :rollup_wallet_address",
            {"tx_hash": tx_hash, "rollup_wallet_address": rollup_wallet_address}
        )
        conn.commit()


# ───────────────────────────────
# 🔄 Vault Withdrawals
# ───────────────────────────────

def insert_vault_withdrawal(withdrawal: VaultWithdrawal):
    row = withdrawal.to_sql_row()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO vault_withdrawals ("
            "recipient_rollup_address, recipient_celestia_address, vault_address, "
            "amount, timestamp, related_utxos_json, tx_hash, processed_by"
            ") VALUES ("
            ":recipient_rollup_address, :recipient_celestia_address, :vault_address, "
            ":amount, :timestamp, :related_utxos_json, :tx_hash, :processed_by"
            ")",
            row
        )
        conn.commit()


def fetch_withdrawals_for(rollup_wallet_address: str) -> list[VaultWithdrawal]:
    with get_connection() as conn:
        conn.row_factory = dict_from_row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM vault_withdrawals "
            "WHERE recipient_rollup_address = :address",
            {"address": rollup_wallet_address}
        )
        return [VaultWithdrawal.from_sql_row(row) for row in cur.fetchall()]


# ───────────────────────────────
# 📜 Receipt Operations
# ───────────────────────────────

def insert_receipt(receipt: ReceiptProof):
    row = receipt.to_sql_row()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO receipts ("
            "receipt_id, txid, block_height, timestamp, "
            "provider, amount, endpoint, full_json"
            ") VALUES ("
            ":receipt_id, :txid, :block_height, :timestamp, "
            ":provider, :amount, :endpoint, :full_json"
            ")",
            row
        )
        conn.commit()


def fetch_receipt(receipt_id: str) -> ReceiptProof | None:
    with get_connection() as conn:
        conn.row_factory = dict_from_row
        cur = conn.cursor()
        cur.execute(
            "SELECT full_json FROM receipts WHERE receipt_id = :rid",
            {"rid": receipt_id}
        )
        r = cur.fetchone()
        return ReceiptProof.from_sql_row(r) if r else None