#!/usr/bin/env python3
"""
Vault watcher daemon for Fontana.

This script monitors a vault address on Celestia for new deposits
and processes them through the bridge interface to the rollup.
"""

import os
import time
import logging
import threading
import sqlite3
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from fontana.core.ledger.ledger import Ledger
from fontana.bridge.handler import handle_deposit_received
from fontana.bridge.celestia.account_client import CelestiaAccountClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vault_watcher")

# Default DB file location
DEFAULT_DB_PATH = "vault_watcher.db"


class VaultWatcher:
    """
    Daemon for monitoring the Celestia vault address for deposits.

    This class handles polling the Celestia blockchain for new deposits to the vault,
    recording them in a local database, and forwarding them to the bridge handler.
    """

    def __init__(
        self,
        vault_address: str,
        l1_node_url: str,
        ledger: Ledger,
        poll_interval: int = 60,
        db_path: str = DEFAULT_DB_PATH
    ):
        """
        Initialize the vault watcher.

        Args:
            vault_address: Celestia account address to monitor for deposits
            l1_node_url: URL of the Celestia node API (REST)
            ledger: Ledger instance to process deposits
            poll_interval: Time in seconds between polling for new deposits
            db_path: Path to the SQLite database file
        """
        self.vault_address = vault_address
        self.l1_node_url = l1_node_url
        self.poll_interval = poll_interval
        self.ledger = ledger
        self.db_path = db_path
        self.is_running = False
        self.monitor_thread = None

        # Initialize database
        self._init_db()

        # Initialize L1 client if URL is provided
        if l1_node_url:
            try:
                self.l1_client = CelestiaAccountClient(l1_node_url)
                logger.info(f"Connected to Celestia node at {l1_node_url}")
            except Exception as e:
                logger.error(f"Failed to connect to Celestia node: {str(e)}")
                raise
        else:
            logger.warning("No L1 node URL provided. Using mock implementation.")
            self.l1_client = None

    def _init_db(self):
        """Initialize the SQLite database with required tables."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create table for tracking processed deposits
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS vault_deposits (
                    l1_tx_hash TEXT PRIMARY KEY,
                    recipient_address TEXT NOT NULL,
                    amount REAL NOT NULL,
                    l1_block_height INTEGER NOT NULL,
                    l1_block_time INTEGER NOT NULL,
                    processed_time INTEGER NOT NULL
                )
                """)
                
                # Create table for system variables
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_vars (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """)
                
                conn.commit()
                logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")
            raise

    def _get_last_processed_height(self) -> int:
        """
        Get the last processed L1 block height from the database.
        
        Returns:
            int: The last processed block height, or 0 if none found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM system_vars WHERE key = 'last_l1_height_processed'")
                result = cursor.fetchone()
                
                if result:
                    return int(result[0])
                else:
                    # Initialize with 0 if not found
                    cursor.execute(
                        "INSERT INTO system_vars (key, value) VALUES ('last_l1_height_processed', '0')"
                    )
                    conn.commit()
                    return 0
        except Exception as e:
            logger.error(f"Error getting last processed height: {str(e)}")
            return 0

    def _update_last_processed_height(self, height: int):
        """
        Update the last processed L1 block height in the database.
        
        Args:
            height: The new block height to record
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE system_vars SET value = ? WHERE key = 'last_l1_height_processed'",
                    (str(height),)
                )
                
                # If no rows were updated, insert a new record
                if cursor.rowcount == 0:
                    cursor.execute(
                        "INSERT INTO system_vars (key, value) VALUES ('last_l1_height_processed', ?)",
                        (str(height),)
                    )
                
                conn.commit()
        except Exception as e:
            logger.error(f"Error updating last processed height: {str(e)}")

    def _get_current_l1_height(self) -> int:
        """
        Get the current block height from the L1 chain.
        
        Returns:
            int: Current block height
        """
        if self.l1_client:
            try:
                return self.l1_client.get_current_height()
            except Exception as e:
                logger.error(f"Error getting current L1 height: {str(e)}")
                return 0
        else:
            # Mock implementation for testing
            return self._get_last_processed_height() + 30

    def _get_deposits_in_range(self, start_height: int, end_height: int) -> List[Dict[str, Any]]:
        """
        Get deposits in the specified block height range.
        
        Args:
            start_height: Start block height (inclusive)
            end_height: End block height (inclusive)
            
        Returns:
            List[Dict[str, Any]]: List of deposit transactions
        """
        if self.l1_client:
            try:
                deposits = self.l1_client.get_deposits_since_height(
                    self.vault_address, start_height, end_height
                )
                return deposits
            except Exception as e:
                logger.error(f"Error getting deposits from L1: {str(e)}")
                return []
        else:
            # Mock implementation for testing
            return []

    def _is_deposit_processed(self, tx_hash: str) -> bool:
        """
        Check if a deposit has already been processed.
        
        Args:
            tx_hash: L1 transaction hash
            
        Returns:
            bool: True if already processed, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM vault_deposits WHERE l1_tx_hash = ?",
                    (tx_hash,)
                )
                result = cursor.fetchone()
                return result[0] > 0
        except Exception as e:
            logger.error(f"Error checking if deposit is processed: {str(e)}")
            return False

    def _record_deposit(self, deposit: Dict[str, Any]) -> bool:
        """
        Record a processed deposit in the database.
        
        Args:
            deposit: Deposit details
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO vault_deposits 
                    (l1_tx_hash, recipient_address, amount, l1_block_height, l1_block_time, processed_time) 
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        deposit["l1_tx_hash"],
                        deposit["recipient_address"],
                        deposit["amount"],
                        deposit["l1_block_height"],
                        deposit["l1_block_time"],
                        int(time.time())
                    )
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error recording deposit: {str(e)}")
            return False

    def _process_deposit(self, deposit: Dict[str, Any]) -> bool:
        """
        Process a new deposit.
        
        This checks if the deposit has already been processed,
        records it in the database, and forwards it to the bridge handler.
        
        Args:
            deposit: Deposit details
            
        Returns:
            bool: True if processing was successful, False otherwise
        """
        tx_hash = deposit["l1_tx_hash"]
        
        # Check if already processed
        if self._is_deposit_processed(tx_hash):
            logger.info(f"Deposit {tx_hash} already processed, skipping")
            return True
        
        # Record the deposit in the database
        if not self._record_deposit(deposit):
            logger.error(f"Failed to record deposit {tx_hash}")
            return False
        
        # Forward to bridge handler
        logger.info(f"Processing deposit: {deposit}")
        result = handle_deposit_received(deposit, self.ledger)
        
        if result:
            logger.info(f"Successfully processed deposit {tx_hash}")
        else:
            logger.error(f"Failed to process deposit {tx_hash} through bridge handler")
        
        return result

    def _run_loop(self):
        """Main monitoring loop that runs in a separate thread."""
        while self.is_running:
            try:
                # Get the last processed height
                last_height = self._get_last_processed_height()
                
                # Get current height
                current_height = self._get_current_l1_height()
                
                if current_height <= last_height:
                    logger.debug(f"No new blocks to process. Current: {current_height}, Last: {last_height}")
                    time.sleep(self.poll_interval)
                    continue
                
                # Define batch size for processing (don't process too many blocks at once)
                batch_size = 100
                end_height = min(current_height, last_height + batch_size)
                
                logger.info(f"Checking for deposits from block {last_height + 1} to {end_height}")
                
                # Get deposits in the range
                deposits = self._get_deposits_in_range(last_height + 1, end_height)
                
                if deposits:
                    logger.info(f"Found {len(deposits)} new deposits")
                    
                    # Process each deposit
                    for deposit in deposits:
                        self._process_deposit(deposit)
                
                # Update the last processed height
                self._update_last_processed_height(end_height)
                
            except Exception as e:
                logger.error(f"Error in vault watcher loop: {str(e)}")
            
            # Sleep before next check
            time.sleep(self.poll_interval)

    def start(self):
        """Start the monitoring thread."""
        if self.is_running:
            logger.warning("Vault watcher is already running")
            return
        
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._run_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        logger.info("Vault watcher started")

    def stop(self):
        """Stop the monitoring thread."""
        if not self.is_running:
            logger.warning("Vault watcher is not running")
            return
        
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join()
            self.monitor_thread = None
        logger.info("Vault watcher stopped")


def main():
    """Main entry point for the vault watcher daemon."""
    # Get configuration from environment variables
    vault_address = os.environ.get("L1_VAULT_ADDRESS")
    node_url = os.environ.get("L1_NODE_URL", "http://celestia-node:1317")
    poll_interval = int(os.environ.get("L1_POLL_INTERVAL", "60"))
    db_path = os.environ.get("VAULT_WATCHER_DB", DEFAULT_DB_PATH)
    
    if not vault_address:
        logger.error("L1_VAULT_ADDRESS environment variable is required")
        return
    
    # Import and initialize ledger
    try:
        from fontana.core.ledger.ledger import Ledger
        ledger = Ledger()
    except Exception as e:
        logger.error(f"Failed to initialize ledger: {str(e)}")
        return
    
    # Create and start vault watcher
    try:
        watcher = VaultWatcher(
            vault_address=vault_address,
            l1_node_url=node_url,
            ledger=ledger,
            poll_interval=poll_interval,
            db_path=db_path
        )
        watcher.start()
        
        # Keep the main thread running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down vault watcher...")
            watcher.stop()
            
    except Exception as e:
        logger.error(f"Error running vault watcher: {str(e)}")


if __name__ == "__main__":
    main()
