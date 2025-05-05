"""
Block generator for the Fontana system.

This module provides a simplified block generator that creates blocks at
regular intervals using processed transactions.
"""
import time
import threading
import logging
import hashlib
import json
from typing import List, Optional

from fontana.core.config import config
from fontana.core.db import db
from fontana.core.models.block import Block, BlockHeader
from fontana.core.models.transaction import SignedTransaction
from fontana.core.ledger import Ledger
from fontana.core.block_generator.processor import TransactionProcessor
from fontana.core.notifications import NotificationManager, NotificationType
from fontana.core.da import CelestiaClient

# Set up logging
logger = logging.getLogger(__name__)


class BlockGenerationError(Exception):
    """Exception raised when block generation fails."""
    pass


class BlockGenerator:
    """
    Block generator for the Fontana system.
    
    This class creates blocks at regular intervals using transactions
    that have been processed and queued by the transaction processor.
    """
    
    def __init__(self, ledger: Ledger, processor: TransactionProcessor, 
                 notification_manager: Optional[NotificationManager] = None,
                 celestia_client: Optional[CelestiaClient] = None):
        """Initialize the block generator.
        
        Args:
            ledger: Ledger instance for transaction validation and state updates
            processor: Transaction processor for pending transactions
            notification_manager: Optional notification manager for event notifications
            celestia_client: Optional Celestia client for DA layer submissions
        """
        self.ledger = ledger
        self.processor = processor
        self.notification_manager = notification_manager
        self.celestia_client = celestia_client
        self.is_running = False
        self.thread = None
        self.block_interval = config.block_interval_seconds
        self.max_block_size = config.max_block_transactions
        logger.info(f"Block generator initialized with interval={self.block_interval}s, "
                   f"max_block_size={self.max_block_size}")
    
    def create_block_header(self, height: int, prev_hash: str, state_root: str, 
                           transactions: List[SignedTransaction]) -> BlockHeader:
        """Create a new block header.
        
        Args:
            height: Block height
            prev_hash: Previous block hash
            state_root: State root after applying transactions
            transactions: List of transactions in the block
            
        Returns:
            BlockHeader: The new block header
        """
        # Calculate timestamp
        timestamp = int(time.time())
        
        # Create header
        header = BlockHeader(
            height=height,
            prev_hash=prev_hash,
            state_root=state_root,
            timestamp=timestamp,
            tx_count=len(transactions),
            # For now, we'll use empty values for these fields
            blob_ref="",
            fee_schedule_id=str(config.fee_schedule_id)
        )
        
        # Calculate header hash
        header_dict = header.model_dump()
        header_dict.pop("hash", None)  # Exclude hash field if present
        header_json = json.dumps(header_dict, sort_keys=True)
        header.hash = hashlib.sha256(header_json.encode()).hexdigest()
        
        return header
    
    def generate_block(self) -> Optional[Block]:
        """Generate a new block from pending transactions.
        
        Returns:
            Optional[Block]: The generated block, or None if no transactions
        """
        try:
            # Get latest block from DB
            latest_block = db.get_latest_block()
            height = latest_block["height"] + 1 if latest_block else 0
            prev_hash = latest_block["hash"] if latest_block else ""
            
            # Get pending transactions
            pending_txs = self.processor.get_pending_transactions(limit=self.max_block_size)
            
            # If there are no pending transactions, return None or create an empty block
            # depending on your preferred approach
            if not pending_txs:
                logger.info("No pending transactions, skipping block generation")
                return None
            
            # Apply transactions to the ledger
            applied_txs = []
            applied_tx_ids = []
            
            for tx in pending_txs:
                try:
                    # Apply transaction to update state
                    if self.ledger.apply_transaction(tx):
                        applied_txs.append(tx)
                        applied_tx_ids.append(tx.txid)
                        
                        # Send notification that transaction was included
                        if self.notification_manager:
                            self.notification_manager.notify(
                                NotificationType.TRANSACTION_INCLUDED,
                                {
                                    "txid": tx.txid,
                                    "block_height": height,
                                    "sender": tx.sender_address,
                                    "status": "applied"
                                }
                            )
                    else:
                        logger.warning(f"Failed to apply transaction {tx.txid}")
                except Exception as e:
                    logger.error(f"Error applying transaction {tx.txid}: {str(e)}")
            
            # If no transactions were applied, return None
            if not applied_txs:
                logger.warning("No transactions could be applied, skipping block generation")
                return None
            
            # Get state root after applying transactions
            state_root = self.ledger.get_current_state_root()
            
            # Create block header
            header = self.create_block_header(
                height=height,
                prev_hash=prev_hash,
                state_root=state_root,
                transactions=applied_txs
            )
            
            # Create the block
            block = Block(header=header, transactions=applied_txs)
            
            # Persist block to database
            db.insert_block(block)
            
            # Clear processed transactions
            self.processor.clear_processed_transactions(applied_tx_ids)
            
            # Send notification that block was created
            if self.notification_manager:
                self.notification_manager.notify(
                    NotificationType.BLOCK_CREATED,
                    {
                        "height": block.header.height,
                        "hash": block.header.hash,
                        "tx_count": len(applied_txs),
                        "state_root": state_root,
                        "transaction_ids": applied_tx_ids
                    }
                )
            
            logger.info(f"Generated block {block.header.height} with {len(applied_txs)} transactions")
            
            # Submit block to Celestia DA layer if client is available
            celestia_namespace_id = None
            if self.celestia_client:
                try:
                    celestia_namespace_id = self.celestia_client.submit_block(block)
                    if celestia_namespace_id:
                        logger.info(f"Block {block.header.height} submitted to Celestia with namespace ID: {celestia_namespace_id}")
                except Exception as e:
                    # Log but don't fail - Celestia submissions can be retried
                    logger.error(f"Failed to submit block {block.header.height} to Celestia: {str(e)}")
            
            return block
            
        except Exception as e:
            logger.error(f"Error generating block: {str(e)}")
            raise BlockGenerationError(f"Failed to generate block: {str(e)}")
    
    def _block_generation_loop(self) -> None:
        """Main block generation loop."""
        logger.info("Block generation loop started")
        
        while self.is_running:
            try:
                # Generate a block
                self.generate_block()
                
                # Wait for the next block interval
                time.sleep(self.block_interval)
            except Exception as e:
                logger.error(f"Error in block generation loop: {str(e)}")
                time.sleep(5)  # Wait a bit before retrying
    
    def start(self) -> None:
        """Start the block generator daemon."""
        if self.is_running:
            logger.warning("Block generator is already running")
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._block_generation_loop)
        self.thread.daemon = True
        self.thread.start()
        
        logger.info("Block generator daemon started")
    
    def stop(self) -> None:
        """Stop the block generator daemon."""
        if not self.is_running:
            logger.warning("Block generator is not running")
            return
        
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        
        logger.info("Block generator daemon stopped")
