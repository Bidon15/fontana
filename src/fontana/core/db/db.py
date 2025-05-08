import sqlite3
import os
from fontana.core.config import config

from fontana.core.models.utxo import UTXO
from fontana.core.models.transaction import SignedTransaction
from fontana.core.models.block import Block
from fontana.core.models.vault import VaultDeposit, VaultWithdrawal
from fontana.core.models.receipt import ReceiptProof


def get_connection():
    return sqlite3.connect(config.db_path)


def dict_from_row(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


# ───────────────────────────────
# 🏗️  Initialization
# ───────────────────────────────


def init_db():
    # Ensure the database directory exists
    os.makedirs(config.db_path.parent, exist_ok=True)

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
            "signature TEXT, "
            "block_height INTEGER"
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
            row,
        )
        conn.commit()


def fetch_unspent_utxos(address: str, include_pending: bool = False) -> list[UTXO]:
    """Fetch all unspent UTXOs for a given address, optionally excluding those in pending transactions.

    Args:
        address: The recipient address
        include_pending: If False (default), exclude UTXOs that are referenced in pending transactions

    Returns:
        List[UTXO]: List of unspent UTXOs
    """
    with get_connection() as conn:
        conn.row_factory = dict_from_row
        cur = conn.cursor()

        if include_pending:
            # Just get unspent UTXOs without considering pending transactions
            cur.execute(
                "SELECT * FROM utxos WHERE recipient = :recipient AND status = 'unspent'",
                {"recipient": address},
            )
        else:
            # Get unspent UTXOs that are not referenced in pending transactions
            # This more complex query joins with pending transactions to exclude UTXOs that
            # are already allocated but not yet confirmed in a block
            cur.execute(
                """
                SELECT u.* FROM utxos u 
                WHERE u.recipient = :recipient AND u.status = 'unspent' 
                AND NOT EXISTS (
                    SELECT 1 FROM transactions tx 
                    JOIN json_each(tx.inputs_json) as inputs 
                    WHERE tx.block_height IS NULL 
                    AND json_extract(inputs.value, '$.txid') = u.txid 
                    AND json_extract(inputs.value, '$.output_index') = u.output_index
                )
                """,
                {"recipient": address},
            )

        return [UTXO.from_sql_row(row) for row in cur.fetchall()]


def mark_utxo_spent(txid: str, output_index: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE utxos SET status = 'spent' "
            "WHERE txid = :txid AND output_index = :output_index",
            {"txid": txid, "output_index": output_index},
        )
        conn.commit()


# ───────────────────────────────
# 🧾 Transaction Ledger
# ───────────────────────────────


def insert_transaction(tx: SignedTransaction):
    import logging

    logger = logging.getLogger(__name__)

    logger.info(f"Inserting transaction {tx.txid} to database")
    logger.info(f"  - Sender: {tx.sender_address}")
    logger.info(
        f"  - Inputs: {len(tx.inputs)}, Outputs: {len(tx.outputs)}, Fee: {tx.fee}"
    )

    row = tx.to_sql_row()
    row["block_height"] = None

    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO transactions ("
                "txid, sender_address, inputs_json, outputs_json, "
                "fee, payload_hash, timestamp, signature, block_height"
                ") VALUES ("
                ":txid, :sender_address, :inputs_json, :outputs_json, "
                ":fee, :payload_hash, :timestamp, :signature, :block_height"
                ")",
                row,
            )
            conn.commit()
            logger.info(f"✅ Transaction {tx.txid} successfully inserted into database")
    except Exception as e:
        logger.error(f"❌ Failed to insert transaction {tx.txid}: {str(e)}")
        raise


def fetch_uncommitted_transactions(limit: int) -> list[SignedTransaction]:
    """
    Returns the oldest `limit` TXs which have not yet been included in any block.
    """
    import logging

    logger = logging.getLogger(__name__)

    logger.debug(f"Fetching up to {limit} uncommitted transactions from database")

    try:
        with get_connection() as conn:
            conn.row_factory = dict_from_row
            cur = conn.cursor()

            # First check if the table exists
            cur.execute(
                "SELECT * FROM transactions WHERE block_height IS NULL LIMIT :limit",
                {"limit": limit},
            )

            # Get raw transaction data
            raw_txs = cur.fetchall()

            # Only log at INFO level if we found transactions
            tx_count = len(raw_txs)
            if tx_count > 0:
                logger.debug(f"Found {tx_count} uncommitted transactions in database")
            else:
                logger.debug(f"Found 0 uncommitted transactions in database")

            # Parse transactions
            result = []
            for row in raw_txs:
                try:
                    tx = SignedTransaction.from_sql_row(row)
                    # Only log detailed transaction info at DEBUG level
                    logger.debug(
                        f"Loaded TX: {tx.txid[:8]}... from {tx.sender_address[:8]}..."
                    )
                    result.append(tx)
                except Exception as e:
                    logger.error(
                        f"Failed to parse transaction {row.get('txid')}: {str(e)}"
                    )

            # Only log at INFO level if we found transactions
            if result:
                logger.debug(f"Processing {len(result)} uncommitted transactions")

            return result
    except Exception as e:
        logger.error(f"❌ Error fetching uncommitted transactions: {str(e)}")
        return []


def save_block(block: Block):
    """
    Save a block to the database and mark its transactions as committed.
    If a block with the same height already exists, it will be updated if necessary.

    Args:
        block: The block to save
    """
    import logging
    import json
    import sqlite3

    logger = logging.getLogger(__name__)

    logger.info(
        f"Saving block {block.header.height} with {len(block.transactions)} transactions"
    )

    # Convert the block header to JSON
    header_json = json.dumps(
        {
            "height": block.header.height,
            "hash": block.header.hash,
            "prev_hash": block.header.prev_hash,
            "timestamp": block.header.timestamp,
            "state_root": block.header.state_root,
            "tx_count": block.header.tx_count,
            "fee_schedule_id": block.header.fee_schedule_id,
        }
    )

    # Convert transactions to JSON
    txs_json = json.dumps([tx.model_dump() for tx in block.transactions])

    # Prepare the block data according to the actual database schema
    block_data = {
        "height": block.header.height,
        "header_json": header_json,
        "txs_json": txs_json,
        "committed": 1,  # Mark as committed
        "blob_ref": (
            block.header.blob_ref if hasattr(block.header, "blob_ref") else None
        ),
    }

    # Save block and its transactions
    with get_connection() as conn:
        try:
            # First check if a block with this height already exists
            cur = conn.cursor()
            cur.execute(
                "SELECT height FROM blocks WHERE height = :height",
                {"height": block.header.height},
            )
            existing_block = cur.fetchone()

            if existing_block:
                # Block already exists - respect immutability
                logger.info(
                    f"Block {block.header.height} already exists, maintaining immutability"
                )

                # The only field we might want to update is the blob_ref after Celestia submission
                if hasattr(block.header, "blob_ref") and block.header.blob_ref:
                    logger.info(
                        f"Updating blob reference for block {block.header.height}"
                    )
                    cur.execute(
                        "UPDATE blocks SET blob_ref = :blob_ref WHERE height = :height AND (blob_ref IS NULL OR blob_ref = '')",
                        {
                            "height": block.header.height,
                            "blob_ref": block.header.blob_ref,
                        },
                    )

                # Return success - we've respected immutability
                return True
            else:
                # Insert new block
                cur.execute(
                    "INSERT INTO blocks ("
                    "height, header_json, txs_json, committed, blob_ref"
                    ") VALUES ("
                    ":height, :header_json, :txs_json, :committed, :blob_ref"
                    ")",
                    block_data,
                )

            conn.commit()

            # Mark transactions as committed
            txids = [tx.txid for tx in block.transactions]
            if txids:
                # Use mark_transactions_committed helper
                mark_transactions_committed(txids, block.header.height)
                logger.info(
                    f"Marked {len(txids)} transactions as committed in block {block.header.height}"
                )

            return True
        except sqlite3.IntegrityError as e:
            # Another case of duplicate blocks (race condition)
            conn.rollback()
            if "UNIQUE constraint failed" in str(e):
                logger.warning(
                    f"Block {block.header.height} already exists (concurrent insert), skipping"
                )
                return True
            else:
                logger.error(
                    f"Database integrity error saving block {block.header.height}: {str(e)}"
                )
                raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save block {block.header.height}: {str(e)}")
            raise

            conn.commit()
            logger.info(f"Successfully saved block {block.header.height} to database")
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save block {block.header.height}: {str(e)}")
            return False


def update_block_blob_ref(height: int, blob_ref: str):
    """
    Update the blob reference for a block after Celestia submission.
    """
    import logging

    logger = logging.getLogger(__name__)

    logger.info(f"Updating blob reference for block {height}: {blob_ref}")

    with get_connection() as conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE blocks SET blob_ref = :blob_ref WHERE height = :height",
                {"height": height, "blob_ref": blob_ref},
            )
            conn.commit()
            logger.info(f"Successfully updated blob reference for block {height}")
            return True
        except Exception as e:
            conn.rollback()
            logger.error(
                f"Failed to update blob reference for block {height}: {str(e)}"
            )
            return False


def purge_invalid_transactions():
    """
    Remove invalid or corrupt transactions from the database.
    This helps clean up transactions that can't be processed.
    Also identifies and removes transactions that attempt to double-spend UTXOs.
    """
    import logging
    import json
    from fontana.core.models.transaction import SignedTransaction
    from fontana.core.db.db_extensions import fetch_utxo

    logger = logging.getLogger(__name__)

    logger.debug("Purging invalid transactions from database")

    deleted_count = 0
    double_spend_count = 0

    with get_connection() as conn:
        try:
            cur = conn.cursor()
            # Delete transactions with missing required fields
            cur.execute(
                "DELETE FROM transactions WHERE txid IS NULL OR sender_address IS NULL OR inputs_json IS NULL"
            )
            deleted_count = cur.rowcount
            conn.commit()

            # Now check for double-spend attempts
            # 1. Get all uncommitted transactions
            cur.execute(
                "SELECT txid, sender_address, inputs_json, outputs_json, fee, payload_hash, "
                "timestamp, signature, block_height FROM transactions WHERE block_height IS NULL"
            )
            rows = cur.fetchall()

            # Track which UTXOs have been spent
            spent_utxos = set()
            txids_to_remove = []

            # First, find UTXOs that are already spent in committed transactions
            cur.execute(
                "SELECT inputs_json FROM transactions WHERE block_height IS NOT NULL"
            )
            committed_rows = cur.fetchall()

            for row in committed_rows:
                try:
                    inputs_data = json.loads(row[0])
                    for inp in inputs_data:
                        spent_utxos.add(f"{inp['txid']}:{inp['output_index']}")
                except Exception as e:
                    logger.error(
                        f"Error parsing committed transaction inputs: {str(e)}"
                    )

            logger.debug(
                f"Found {len(spent_utxos)} already spent UTXOs in committed transactions"
            )

            # For batch transactions, we need to build a dependency graph
            # This maps txid -> list of txids it depends on
            dependency_graph = {}
            # Maps txid -> row data for lookup
            tx_data = {}
            # Build a set of all uncommitted txids for quick lookup
            uncommitted_txids = set(row[0] for row in rows)
            
            # First, build the dependency graph
            for row in rows:
                txid = row[0]
                tx_data[txid] = row
                try:
                    # Parse transaction inputs
                    inputs_data = json.loads(row[2])
                    
                    # Track dependencies
                    dependencies = []
                    for inp in inputs_data:
                        input_txid = inp['txid']
                        # If this input comes from another uncommitted tx, it's a dependency
                        if input_txid in uncommitted_txids:
                            dependencies.append(input_txid)
                    
                    # Store in graph
                    dependency_graph[txid] = dependencies
                except Exception as e:
                    logger.error(f"Error parsing transaction {txid} dependencies: {str(e)}")
            
            # Now process uncommitted transactions in dependency order
            processed = set()  # Keep track of processed txids
            
            # Process transactions in dependency order using iterative approach (Kahn's algorithm)
            # First, compute in-degrees for each transaction (number of dependencies)
            in_degree = {txid: 0 for txid in tx_data}
            for txid, deps in dependency_graph.items():
                for dep in deps:
                    in_degree[dep] = in_degree.get(dep, 0) + 1
            
            # Start with transactions that have no dependencies
            queue = [txid for txid, degree in in_degree.items() if degree == 0]
            processed = set()
            
            # Process queue until empty
            while queue:
                txid = queue.pop(0)
                
                # Skip if already processed
                if txid in processed:
                    continue
                
                # Process this transaction
                row = tx_data[txid]
                try:
                    # Parse transaction inputs
                    inputs_data = json.loads(row[2])
                    
                    # Check if any input is already spent
                    is_double_spend = False
                    for inp in inputs_data:
                        utxo_ref = f"{inp['txid']}:{inp['output_index']}"
                        
                        # Check if UTXO is already spent (and not in our dependency chain)
                        if utxo_ref in spent_utxos and inp['txid'] not in dependency_graph.get(txid, []):
                            logger.warning(
                                f"Transaction {txid} attempts to spend already spent UTXO: {utxo_ref}"
                            )
                            is_double_spend = True
                            break
                            
                        # If the input is from another transaction in our batch, skip UTXO existence check
                        if inp['txid'] in uncommitted_txids:
                            continue
                            
                        # Also verify the UTXO exists
                        utxo = fetch_utxo(inp["txid"], inp["output_index"])
                        if not utxo:
                            logger.warning(
                                f"Transaction {txid} references non-existent UTXO: {utxo_ref}"
                            )
                            is_double_spend = True
                            break
                            
                        # Check if UTXO is already marked as spent in the database
                        if utxo and utxo.is_spent():
                            logger.warning(
                                f"Transaction {txid} references spent UTXO in DB: {utxo_ref}"
                            )
                            is_double_spend = True
                            break
                            
                    if is_double_spend:
                        txids_to_remove.append(txid)
                    else:
                        # If not a double spend, mark these UTXOs as spent for subsequent checks
                        for inp in inputs_data:
                            utxo_ref = f"{inp['txid']}:{inp['output_index']}"
                            spent_utxos.add(utxo_ref)
                except Exception as e:
                    logger.error(
                        f"Error checking transaction {txid} for double spends: {str(e)}"
                    )
                    # Add to removal list if we can't properly validate it
                    txids_to_remove.append(txid)
                
                # Mark as processed
                processed.add(txid)
                
                # Add transactions that depend on this one to the queue if all their dependencies are processed
                for dependent in dependency_graph.get(txid, []):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

            # Remove all detected double-spend transactions
            if txids_to_remove:
                placeholders = ",".join(["?" for _ in txids_to_remove])
                cur.execute(
                    f"DELETE FROM transactions WHERE txid IN ({placeholders})",
                    txids_to_remove,
                )
                double_spend_count = cur.rowcount
                conn.commit()
                logger.info(f"Removed {double_spend_count} double-spend transactions")

            total_removed = deleted_count + double_spend_count
            # Only log at INFO level if we actually removed something
            if total_removed > 0:
                logger.info(
                    f"Total purged: {total_removed} transactions ({deleted_count} invalid + {double_spend_count} double-spends)"
                )
            else:
                logger.debug(
                    f"Total purged: 0 transactions (0 invalid + 0 double-spends)"
                )
            return total_removed
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to purge invalid transactions: {str(e)}")
            return 0


def mark_transactions_committed(txids: list[str], height: int):
    """
    Marks the given list of txids as included in block `height`.
    """
    if not txids:
        return

    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Marking {len(txids)} transactions as committed in block {height}")

    placeholders = ",".join(f":tx{i}" for i in range(len(txids)))
    params = {"height": height, **{f"tx{i}": tx for i, tx in enumerate(txids)}}

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE transactions "
            f"SET block_height = :height "
            f"WHERE txid IN ({placeholders})",
            params,
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
            row,
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
            {"height": height, "blob_ref": blob_ref},
        )
        conn.commit()


def get_block_by_height(height: int) -> Block | None:
    with get_connection() as conn:
        conn.row_factory = dict_from_row
        cur = conn.cursor()
        cur.execute("SELECT * FROM blocks WHERE height = :height", {"height": height})
        row = cur.fetchone()
        return Block.from_sql_row(row) if row else None


def get_latest_block():
    """
    Get the latest block from the database.

    Returns:
        dict: The latest block with height and hash, or None if no blocks exist
    """
    with get_connection() as conn:
        conn.row_factory = dict_from_row
        cur = conn.cursor()

        cur.execute(
            "SELECT height, json_extract(header_json, '$.hash') as hash "
            "FROM blocks ORDER BY height DESC LIMIT 1"
        )

        result = cur.fetchone()
        return result


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
            row,
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
            {"tx_hash": tx_hash, "rollup_wallet_address": rollup_wallet_address},
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
            row,
        )
        conn.commit()


def fetch_withdrawals_for(rollup_wallet_address: str) -> list[VaultWithdrawal]:
    with get_connection() as conn:
        conn.row_factory = dict_from_row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM vault_withdrawals "
            "WHERE recipient_rollup_address = :address",
            {"address": rollup_wallet_address},
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
            row,
        )
        conn.commit()


def fetch_receipt(receipt_id: str) -> ReceiptProof | None:
    with get_connection() as conn:
        conn.row_factory = dict_from_row
        cur = conn.cursor()
        cur.execute(
            "SELECT full_json FROM receipts WHERE receipt_id = :rid",
            {"rid": receipt_id},
        )
        r = cur.fetchone()
        return ReceiptProof.from_sql_row(r) if r else None
