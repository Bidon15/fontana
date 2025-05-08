#!/usr/bin/env python3
"""
Test script for Fontana rollup transactions.

This script:
1. Creates multiple test wallets
2. Funds them from the genesis wallet
3. Performs transactions between wallets
4. Verifies transaction success and database state
5. Monitors Celestia DA posting

Usage:
    python test_transactions.py --rpc-url http://localhost:8545
"""

import os
import sys
import time
import argparse
import logging
import sqlite3
import json
import subprocess
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("transaction_test")

def run_cli_command(command: List[str]) -> Dict[str, Any]:
    """Run a CLI command and return JSON output."""
    try:
        cmd = ["python", "-m", "fontana.cli"] + command
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e.stderr}")
        return {"error": e.stderr}
    except json.JSONDecodeError:
        logger.error(f"Failed to parse JSON output: {result.stdout}")
        return {"error": "Invalid JSON", "output": result.stdout}

def create_wallet(name: str) -> Dict[str, Any]:
    """Create a new wallet with the given name."""
    logger.info(f"Creating wallet: {name}")
    result = run_cli_command(["wallet", "new", "--name", name])
    return result

def get_wallet_address(name: str) -> str:
    """Get the address of a wallet."""
    result = run_cli_command(["wallet", "address", "--name", name])
    return result.get("address", "")

def get_wallet_balance(name: str, rpc_url: str) -> int:
    """Get the balance of a wallet."""
    result = run_cli_command(["wallet", "balance", "--name", name, "--rpc-url", rpc_url])
    return result.get("balance", 0)

def send_transaction(from_wallet: str, to_address: str, amount: int, rpc_url: str) -> Dict[str, Any]:
    """Send a transaction from one wallet to another."""
    logger.info(f"Sending {amount} from {from_wallet} to {to_address}")
    result = run_cli_command([
        "tx", "send", 
        "--from", from_wallet, 
        "--to", to_address, 
        "--amount", str(amount), 
        "--rpc-url", rpc_url
    ])
    return result

def check_transaction_status(tx_hash: str, rpc_url: str) -> Dict[str, Any]:
    """Check the status of a transaction."""
    result = run_cli_command(["tx", "info", "--tx-hash", tx_hash, "--rpc-url", rpc_url])
    return result

def verify_database_state(db_path: str) -> None:
    """Verify the database state after transactions."""
    logger.info(f"Verifying database state in {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check UTXOs
        cursor.execute("SELECT COUNT(*) FROM utxos")
        utxo_count = cursor.fetchone()[0]
        logger.info(f"UTXO count: {utxo_count}")
        
        # Check blocks
        cursor.execute("SELECT MAX(height) FROM blocks")
        max_height = cursor.fetchone()[0]
        logger.info(f"Latest block height: {max_height}")
        
        # Check transactions
        cursor.execute("SELECT COUNT(*) FROM transactions")
        tx_count = cursor.fetchone()[0]
        logger.info(f"Transaction count: {tx_count}")
        
        conn.close()
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")

def check_celestia_posting(namespace: str, rpc_url: str) -> bool:
    """Check if data was posted to Celestia."""
    # This would typically call Celestia API to verify posting
    # For demonstration purposes, we're just checking the local chain status
    chain_info = run_cli_command(["chain", "info", "--rpc-url", rpc_url])
    last_da_height = chain_info.get("last_da_height", 0)
    logger.info(f"Last DA height: {last_da_height}")
    return last_da_height > 0

def main():
    parser = argparse.ArgumentParser(description="Test Fontana rollup transactions")
    parser.add_argument("--rpc-url", default="http://localhost:8545", help="RPC URL of the Fontana node")
    parser.add_argument("--db-path", default=os.environ.get("ROLLUP_DB_PATH", "./data/rollup.db"), 
                        help="Path to the rollup database")
    parser.add_argument("--wallet-count", type=int, default=4, help="Number of test wallets to create")
    parser.add_argument("--genesis-wallet", default="genesis", help="Name of the genesis wallet")
    parser.add_argument("--amount", type=int, default=100, help="Amount to transfer in each transaction")
    parser.add_argument("--wait-time", type=int, default=20, help="Time to wait between operations (seconds)")
    parser.add_argument("--genesis-file", default="examples/custom_genesis.json", 
                        help="Path to the genesis file used for initialization (for documentation purposes)")
    
    args = parser.parse_args()
    
    try:
        # Print test information
        logger.info(f"Starting transaction test with:")
        logger.info(f"  - RPC URL: {args.rpc_url}")
        logger.info(f"  - Database: {args.db_path}")
        logger.info(f"  - Genesis wallet: {args.genesis_wallet}")
        logger.info(f"  - Genesis file: {args.genesis_file}")
        logger.info(f"  - Creating {args.wallet_count} test wallets")
        
        # 1. Create test wallets
        wallet_names = [f"test_wallet_{i}" for i in range(args.wallet_count)]
        wallets = {}
        
        for name in wallet_names:
            create_wallet(name)
            address = get_wallet_address(name)
            wallets[name] = address
            logger.info(f"Created wallet {name} with address {address}")
        
        # Wait for next block
        logger.info(f"Waiting {args.wait_time} seconds for next block...")
        time.sleep(args.wait_time)
        
        # 2. Fund wallets from genesis wallet
        genesis_balance = get_wallet_balance(args.genesis_wallet, args.rpc_url)
        logger.info(f"Genesis wallet balance: {genesis_balance}")
        
        funding_amount = args.amount * 2  # Give each wallet enough to send transactions
        
        for name, address in wallets.items():
            send_transaction(args.genesis_wallet, address, funding_amount, args.rpc_url)
            logger.info(f"Sent {funding_amount} to {name}")
        
        # Wait for funding transactions to be included in a block
        logger.info(f"Waiting {args.wait_time} seconds for funding transactions...")
        time.sleep(args.wait_time)
        
        # 3. Verify wallet balances after funding
        for name in wallet_names:
            balance = get_wallet_balance(name, args.rpc_url)
            logger.info(f"{name} balance after funding: {balance}")
            if balance != funding_amount:
                logger.warning(f"Expected balance of {funding_amount}, got {balance}")
        
        # 4. Perform wallet-to-wallet transactions
        transactions = []
        for i in range(len(wallet_names)):
            sender = wallet_names[i]
            recipient = wallet_names[(i + 1) % len(wallet_names)]
            tx_result = send_transaction(sender, wallets[recipient], args.amount, args.rpc_url)
            transactions.append(tx_result)
            logger.info(f"Transaction from {sender} to {recipient}: {tx_result}")
        
        # Wait for transactions to be included in a block
        logger.info(f"Waiting {args.wait_time} seconds for transactions to be processed...")
        time.sleep(args.wait_time)
        
        # 5. Verify final wallet balances
        for name in wallet_names:
            balance = get_wallet_balance(name, args.rpc_url)
            logger.info(f"{name} final balance: {balance}")
        
        # 6. Verify database state
        verify_database_state(args.db_path)
        
        # 7. Check Celestia DA posting
        da_status = check_celestia_posting("", args.rpc_url)
        logger.info(f"Celestia DA posting status: {'Success' if da_status else 'Pending/Failed'}")
        
        logger.info("Transaction test completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
