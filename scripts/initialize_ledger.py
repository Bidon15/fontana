#!/usr/bin/env python3
"""Initialize the Fontana ledger with a genesis state.

This script resets the database and initializes it with the specified genesis file.
"""

import os
import sys
import json
import logging
import argparse
import sqlite3
from pathlib import Path

# Add the project root to the Python path
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from fontana.core.models.utxo import UTXO
from fontana.core.db import db

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("fontana-init")

def parse_args():
    parser = argparse.ArgumentParser(description="Initialize the Fontana ledger with genesis state")
    parser.add_argument("--genesis", type=str, default="examples/custom_genesis.json",
                        help="Path to genesis file (default: examples/custom_genesis.json)")
    parser.add_argument("--force", action="store_true",
                        help="Force reinitialization even if database exists")
    parser.add_argument("--db-path", type=str, default=str(Path.home() / ".fontana" / "ledger.db"),
                        help="Custom database path (default: ~/.fontana/ledger.db)")
    return parser.parse_args()

def init_db_tables(db_path):
    """Create the database tables from scratch."""
    # Make sure the parent directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        
        # Create UTXOs table - EXACT MATCH with db.py
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

        # Create transactions table - EXACT MATCH with db.py
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

        # Create blocks table - EXACT MATCH with db.py
        cur.execute(
            "CREATE TABLE IF NOT EXISTS blocks ("
            "height INTEGER PRIMARY KEY, "
            "header_json TEXT, "
            "txs_json TEXT, "
            "committed INTEGER DEFAULT 0, "
            "blob_ref TEXT"
            ")"
        )

        # Create vault_deposits table - EXACT MATCH with db.py
        cur.execute(
            "CREATE TABLE IF NOT EXISTS vault_deposits ("
            "depositor_address TEXT, "
            "rollup_wallet_address TEXT, "
            "vault_address TEXT, "
            "tx_hash TEXT, "
            "amount REAL, "
            "status TEXT, "
            "celestia_height INTEGER, "
            "timestamp INTEGER"
            ")"
        )

        # Create vault_withdrawals table
        cur.execute(
            "CREATE TABLE IF NOT EXISTS vault_withdrawals ("
            "id TEXT PRIMARY KEY, "
            "rollup_tx_hash TEXT, "
            "celestia_address TEXT, "
            "amount REAL, "
            "status TEXT, "
            "celestia_tx_hash TEXT, "
            "timestamp INTEGER"
            ")"
        )

        # Other tables might be needed but not immediately required
        # for the core functionality
        
        conn.commit()

def initialize_ledger(genesis_file, force=False, db_path=None):
    """Initialize the ledger with genesis state."""
    # Process custom DB path
    if db_path:
        # Set the database path in the environment
        os.environ["ROLLUP_DB_PATH"] = db_path
    
    # Get the final DB path (either from environment or default)
    db_path = os.environ.get("ROLLUP_DB_PATH", str(Path.home() / ".fontana" / "ledger.db"))
    
    # Expand ~ if present
    db_path = os.path.expanduser(db_path)
    logger.info(f"Using database path: {db_path}")
    
    # Check if database exists
    if os.path.exists(db_path) and not force:
        logger.info(f"Database already exists at {db_path}. Use --force to overwrite.")
        return False
    
    # Remove existing database if it exists
    if os.path.exists(db_path):
        logger.info(f"Removing existing database at {db_path}")
        os.remove(db_path)
    
    # Initialize a new database
    logger.info(f"Initializing database at {db_path}")
    init_db_tables(db_path)
    
    try:
        # Load genesis file
        with open(genesis_file, 'r') as f:
            genesis_data = json.load(f)
        
        # Process initial UTXOs
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            
            # Check if genesis has 'allocations' format
            if "allocations" in genesis_data:
                for address, amount in genesis_data["allocations"].items():
                    logger.info(f"Creating genesis allocation: {amount} to {address}")
                    
                    # Create a genesis UTXO directly in the database
                    cur.execute(
                        "INSERT INTO utxos (txid, output_index, recipient, amount, status) "
                        "VALUES (?, ?, ?, ?, ?)",
                        ("genesis", 0, address, float(amount), "unspent")
                    )
            
            # Check if genesis has 'utxos' array format
            elif "utxos" in genesis_data and isinstance(genesis_data["utxos"], list):
                for output_index, utxo in enumerate(genesis_data["utxos"]):
                    if "recipient" in utxo and "amount" in utxo:
                        recipient = utxo["recipient"]
                        amount = float(utxo["amount"])
                        logger.info(f"Creating genesis UTXO: {amount} to {recipient}")
                        
                        # Create a genesis UTXO directly in the database
                        cur.execute(
                            "INSERT INTO utxos (txid, output_index, recipient, amount, status) "
                            "VALUES (?, ?, ?, ?, ?)",
                            ("genesis", output_index, recipient, amount, "unspent")
                        )
            else:
                logger.error("Genesis file has invalid format. Expected 'allocations' or 'utxos'.")
                return False
            
            conn.commit()
            
        logger.info("Genesis state applied successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error initializing ledger: {str(e)}")
        return False

if __name__ == "__main__":
    args = parse_args()
    
    if initialize_ledger(args.genesis, args.force, args.db_path):
        logger.info("Ledger initialized successfully")
    else:
        logger.error("Failed to initialize ledger")
        sys.exit(1)
