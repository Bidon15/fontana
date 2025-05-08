#!/usr/bin/env python
"""
Debug Transaction Flow Script

This script helps diagnose issues with transaction processing in the Fontana rollup.
It traces transactions from insertion in the database through the batching process
and identifies potential blockers.
"""
import os
import sys
import time
import logging
import sqlite3
import json
from datetime import datetime, timezone
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("debug_tx_flow.log")
    ]
)
logger = logging.getLogger("tx_debug")

# Add the project root to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fontana.core.db import db
from fontana.core.config import config
from fontana.core.models.transaction import SignedTransaction

def check_database_schema():
    """Check if database schema exists and is correctly set up."""
    logger.info("Checking database schema...")
    
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            
            # Check if all required tables exist
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}
            
            required_tables = {'blocks', 'transactions', 'utxos'}
            missing_tables = required_tables - tables
            
            if missing_tables:
                logger.error(f"❌ Missing required tables: {missing_tables}")
                return False
                
            logger.info(f"✅ All required tables exist: {', '.join(required_tables)}")
            
            # Check transactions table schema
            cur.execute("PRAGMA table_info(transactions)")
            columns = {row[1] for row in cur.fetchall()}
            
            required_columns = {
                'txid', 'sender_address', 'inputs_json', 'outputs_json',
                'fee', 'payload_hash', 'timestamp', 'signature', 'block_height'
            }
            
            missing_columns = required_columns - columns
            if missing_columns:
                logger.error(f"❌ Transactions table missing columns: {missing_columns}")
                return False
                
            logger.info("✅ Transactions table schema is correct")
            return True
            
    except Exception as e:
        logger.error(f"❌ Database error: {str(e)}")
        return False

def check_uncommitted_transactions():
    """Check for uncommitted transactions in the database."""
    logger.info("Checking for uncommitted transactions...")
    
    try:
        with db.get_connection() as conn:
            conn.row_factory = db.dict_from_row
            cur = conn.cursor()
            
            # Count uncommitted transactions
            cur.execute("SELECT COUNT(*) as count FROM transactions WHERE block_height IS NULL")
            count = cur.fetchone()['count']
            
            if count == 0:
                logger.info("No uncommitted transactions found in the database")
                return []
                
            logger.info(f"Found {count} uncommitted transactions")
            
            # Fetch details of uncommitted transactions
            cur.execute(
                "SELECT * FROM transactions WHERE block_height IS NULL ORDER BY timestamp ASC"
            )
            uncommitted = cur.fetchall()
            
            # Log details of uncommitted transactions
            for i, tx in enumerate(uncommitted[:5]):  # Show first 5
                logger.info(f"TX {i+1}: {tx['txid']} from {tx['sender_address']}")
                
                # Parse and show inputs and outputs
                try:
                    inputs = json.loads(tx['inputs_json'])
                    outputs = json.loads(tx['outputs_json'])
                    
                    logger.info(f"  - Inputs: {len(inputs)}, Outputs: {len(outputs)}, Fee: {tx['fee']}")
                    for j, inp in enumerate(inputs[:2]):
                        logger.info(f"  - Input {j+1}: {inp['txid'][:8]}...:{inp['output_index']}")
                except Exception as e:
                    logger.error(f"  - Error parsing inputs/outputs: {str(e)}")
            
            if count > 5:
                logger.info(f"... and {count - 5} more uncommitted transactions")
                
            return uncommitted
            
    except Exception as e:
        logger.error(f"❌ Error checking uncommitted transactions: {str(e)}")
        return []

def create_test_transaction():
    """Create a test transaction and insert it into the database."""
    from fontana.wallet.wallet import Wallet
    from fontana.core.models.utxo import UTXORef
    
    logger.info("Creating a test transaction...")
    
    try:
        # Generate a new wallet for testing
        test_wallet = Wallet.generate()
        sender_address = test_wallet.get_address()
        
        # Create a simple test transaction
        timestamp = int(time.time())
        txid = f"test_tx_{timestamp}"
        
        # Simplified input and output
        inputs = [UTXORef(txid="genesis", output_index=0)]
        outputs = [{"recipient": sender_address, "amount": 10.0}]
        
        # Create transaction message for signing
        tx_data = {
            "sender": sender_address,
            "inputs": [inp.model_dump() for inp in inputs],
            "outputs": outputs,
            "fee": 0.001,
            "timestamp": timestamp
        }
        
        message = json.dumps(tx_data, sort_keys=True).encode()
        payload_hash = ""  # Simplified for test
        signature = ""     # Simplified for test
        
        # Create a simplified transaction
        tx = {
            "txid": txid,
            "sender_address": sender_address,
            "inputs_json": json.dumps([inp.model_dump() for inp in inputs]),
            "outputs_json": json.dumps(outputs),
            "fee": 0.001,
            "payload_hash": payload_hash,
            "timestamp": timestamp,
            "signature": signature,
            "block_height": None
        }
        
        # Insert directly to database
        with db.get_connection() as conn:
            cur = conn.cursor()
            
            # Create placeholders and values for the SQL query
            placeholders = ", ".join(f":{k}" for k in tx.keys())
            columns = ", ".join(tx.keys())
            
            cur.execute(
                f"INSERT INTO transactions ({columns}) VALUES ({placeholders})",
                tx
            )
            conn.commit()
            
        logger.info(f"✅ Test transaction {txid} created and inserted into database")
        return txid
        
    except Exception as e:
        logger.error(f"❌ Error creating test transaction: {str(e)}")
        return None

def check_process_functions():
    """Check if processor and generator functions can access uncommitted transactions."""
    logger.info("Testing transaction processor access...")
    
    try:
        # Import these only when needed to avoid circular imports
        from fontana.core.block_generator.processor import TransactionProcessor
        from fontana.core.ledger import Ledger
        
        # Create a test ledger and processor
        ledger = Ledger()
        processor = TransactionProcessor(ledger)
        
        # Get transaction stats
        stats = processor.get_transaction_stats()
        logger.info(f"Transaction stats from processor: {stats}")
        
        # Try to get pending transactions
        txs = processor.get_pending_transactions(limit=10)
        logger.info(f"Fetched {len(txs)} pending transactions with processor")
        
        return len(txs) > 0
        
    except Exception as e:
        logger.error(f"❌ Error testing transaction processor: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Debug transaction processing flow")
    parser.add_argument("--create-test", action="store_true", help="Create a test transaction")
    parser.add_argument("--check-schema", action="store_true", help="Check database schema")
    parser.add_argument("--check-transactions", action="store_true", help="Check for uncommitted transactions")
    parser.add_argument("--check-processor", action="store_true", help="Test transaction processor")
    parser.add_argument("--all", action="store_true", help="Run all checks")
    
    args = parser.parse_args()
    
    # Default to running all checks if none specified
    run_all = args.all or not (args.create_test or args.check_schema or 
                               args.check_transactions or args.check_processor)
    
    logger.info("=== Fontana Transaction Flow Debugging ===")
    logger.info(f"Database path: {config.db_path}")
    
    if args.check_schema or run_all:
        check_database_schema()
        
    if args.check_transactions or run_all:
        check_uncommitted_transactions()
        
    if args.create_test or run_all:
        create_test_transaction()
        
    if args.check_processor or run_all:
        check_process_functions()
        
    logger.info("Debug process complete. Check the logs for details.")

if __name__ == "__main__":
    main()
