"""
Transaction processor for the Fontana system.

This module provides functionality for processing transactions directly,
checking fee requirements, and preparing them for inclusion in blocks.
"""
import logging
import time
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timezone

from fontana.core.config import config
from fontana.core.models.transaction import SignedTransaction
from fontana.core.ledger import Ledger, TransactionValidationError
from fontana.core.notifications import NotificationManager, NotificationType
from fontana.core.db import db

# Set up logging
logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Base exception for transaction processing errors."""
    pass


class InsufficientFeeError(ProcessingError):
    """Exception raised when a transaction doesn't meet the minimum fee requirement."""
    pass


class TransactionProcessor:
    """
    Transaction processor for the Fontana system.
    
    This class handles direct transaction processing, including:
    - Fee validation
    - Transaction validation through the ledger
    - Queuing valid transactions for inclusion in blocks
    - Transaction metadata tracking for efficient batching
    """
    
    def __init__(self, ledger: Ledger, notification_manager: Optional[NotificationManager] = None):
        """Initialize the transaction processor.
        
        Args:
            ledger: Ledger instance for transaction validation
            notification_manager: Optional notification manager for event notifications
        """
        self.ledger = ledger
        self.notification_manager = notification_manager
        self.pending_transactions: List[SignedTransaction] = []
        self.processed_txids: Dict[str, Dict[str, Any]] = {}  # Track tx metadata by txid
        self.minimum_fee = config.minimum_transaction_fee
        logger.info(f"Transaction processor initialized with minimum fee={self.minimum_fee}")
    
    def process_transaction(self, tx: SignedTransaction) -> bool:
        """Process a transaction and queue it for inclusion in a block if valid.
        Provides fast response (<100ms) while asynchronously handling batching.
        
        Args:
            tx: Transaction to process
            
        Returns:
            bool: True if the transaction was processed successfully
            
        Raises:
            InsufficientFeeError: If the transaction fee is below the minimum
            ProcessingError: If there's an error during processing
            TransactionValidationError: If the transaction is invalid
        """
        start_time = time.time()
        try:
            # Fast path - check if we've already seen this transaction
            if tx.txid in self.processed_txids:
                logger.info(f"Transaction {tx.txid} already processed, status: {self.processed_txids[tx.txid]['status']}")
                return True
                
            # Quick validations first (these should be very fast)
            # Check minimum fee requirement
            if tx.fee < self.minimum_fee:
                raise InsufficientFeeError(
                    f"Transaction fee {tx.fee} is below minimum {self.minimum_fee}"
                )
            
            # Do basic signature validation without touching the database
            # This allows for very fast response times
            if not tx.verify_signature():
                logger.warning(f"Transaction {tx.txid} has invalid signature")
                return False
            
            # At this point, the transaction looks valid from a basic verification standpoint
            # We'll track it as "accepted" but not yet "confirmed"
            self.processed_txids[tx.txid] = {
                "status": "accepted",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "processing_time_ms": int((time.time() - start_time) * 1000)
            }
            
            # Queue transaction for inclusion in next block
            self.pending_transactions.append(tx)
            
            # Send notification if manager is available
            if self.notification_manager:
                self.notification_manager.send_notification(
                    NotificationType.TRANSACTION_PROCESSED,
                    {"txid": tx.txid, "status": "accepted"}
                )
                
            processing_time = int((time.time() - start_time) * 1000)
            logger.info(f"Transaction {tx.txid} accepted in {processing_time}ms and queued for next block")
            return True
            
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            logger.error(f"Error processing transaction ({processing_time}ms): {str(e)}")
            raise ProcessingError(f"Failed to process transaction: {str(e)}") from e   
    def process_transaction_fast(self, tx: SignedTransaction) -> Dict[str, Any]:
        """Process a transaction with immediate response for fast user feedback.
        
        This method provides near-instant (sub-100ms) feedback to users about transaction
        validity without waiting for block inclusion or Celestia DA commitment.
        
        Args:
            tx: Transaction to process
            
        Returns:
            Dict[str, Any]: Response with status and details
        """
        try:
            # Perform fast validation
            is_valid, reason = self.validate_transaction_fast(tx)
            
            if not is_valid:
                # Transaction failed fast validation
                if self.notification_manager:
                    self.notification_manager.notify(
                        NotificationType.TRANSACTION_REJECTED,
                        {
                            "txid": tx.txid,
                            "reason": reason,
                            "status": "rejected"
                        }
                    )
                
                return {
                    "status": "rejected",
                    "txid": tx.txid,
                    "reason": reason
                }
            
            # Queue transaction for inclusion in the next block
            self.pending_transactions.append(tx)
            
            # Notify of provisional acceptance
            if self.notification_manager:
                self.notification_manager.notify(
                    NotificationType.TRANSACTION_RECEIVED,
                    {
                        "txid": tx.txid,
                        "sender": tx.sender_address,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "status": "provisionally_accepted"
                    }
                )
            
            # Calculate estimated confirmation times
            block_interval = config.block_interval_seconds
            estimated_block_time = block_interval  # Worst case: just missed a block
            estimated_celestia_time = 30  # Typical Celestia inclusion time
            
            # Return immediate response
            return {
                "status": "provisionally_accepted",
                "txid": tx.txid,
                "estimated_block_time": estimated_block_time,
                "estimated_celestia_time": estimated_celestia_time,
                "message": "Transaction validated and queued for inclusion in the next block"
            }
            
        except Exception as e:
            logger.error(f"Error in fast processing for transaction {tx.txid}: {str(e)}")
            
            # Notify of error
            if self.notification_manager:
                self.notification_manager.notify(
                    NotificationType.TRANSACTION_REJECTED,
                    {
                        "txid": tx.txid,
                        "reason": str(e),
                        "status": "error"
                    }
                )
            
            return {
                "status": "error",
                "txid": tx.txid,
                "reason": str(e)
            }
    
    def validate_transaction_fast(self, tx: SignedTransaction) -> Tuple[bool, Optional[str]]:
        """Quickly validate a transaction without applying it to the state.
        
        This method performs lightweight validation checks that can
        complete in milliseconds, suitable for immediate user responses.
        
        Args:
            tx: Transaction to validate
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, reason_if_invalid)
        """
        try:
            # Check minimum fee requirement
            if tx.fee < self.minimum_fee:
                return False, f"Transaction fee {tx.fee} is below minimum {self.minimum_fee}"
            
            # Check if this txid is already in the pending transactions
            if any(pending_tx.txid == tx.txid for pending_tx in self.pending_transactions):
                return False, f"Transaction {tx.txid} is already pending"
            
            # Check signature - this is a basic check that can be done quickly
            # We use the ledger's validate_signature method if available
            if hasattr(self.ledger, '_validate_signature'):
                if not self.ledger._validate_signature(tx):
                    return False, "Invalid signature"
            
            # Check basic transaction structure
            if not tx.inputs or not tx.outputs:
                return False, "Transaction must have inputs and outputs"
            
            # More checks could be added, but we want to keep this fast
            # Full validation will happen when the transaction is included in a block
            
            return True, None
            
        except Exception as e:
            logger.error(f"Error in fast validation for transaction {tx.txid}: {str(e)}")
            return False, str(e)
    
    def get_pending_transactions(self, limit: Optional[int] = None) -> List[SignedTransaction]:
        """Get pending transactions for inclusion in a block.
        
        This method efficiently batches pending transactions up to the specified limit.
        It also updates transaction status metadata for tracking.
        
        Args:
            limit: Maximum number of transactions to return
            
        Returns:
            List[SignedTransaction]: Pending transactions for inclusion in a block
        """
        if not self.pending_transactions:
            return []
        
        # Get transactions for the next block
        if limit is None or limit >= len(self.pending_transactions):
            # Return all pending transactions
            transactions = self.pending_transactions.copy()  # Make a copy to avoid modifying during iteration
            count = len(transactions)
        else:
            # Return only up to the limit
            transactions = self.pending_transactions[:limit].copy()
            count = len(transactions)
            
        # Mark transactions as being included in a block
        for tx in transactions:
            if tx.txid in self.processed_txids:
                self.processed_txids[tx.txid]["status"] = "batched"
                self.processed_txids[tx.txid]["batched_at"] = datetime.now(timezone.utc).isoformat()
                
        # Log the batching operations
        logger.info(f"Batched {count} transactions for inclusion in the next block")
        
        # We leave transactions in the pending list until they're confirmed in a block
        # This ensures we can retry if block generation fails
        return transactions
        
    def clear_processed_transactions(self, txids: List[str]) -> int:
        """Clear transactions that have been successfully included in a block.
        
        Args:
            txids: List of transaction IDs that have been confirmed in a block
            
        Returns:
            int: Number of transactions cleared
        """
        if not txids:
            return 0
            
        # Create a set for O(1) lookups
        txid_set = set(txids)
            
        # Update status for these transactions
        for txid in txids:
            if txid in self.processed_txids:
                self.processed_txids[txid]["status"] = "confirmed"
                self.processed_txids[txid]["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        
        # Remove these transactions from the pending list
        before_count = len(self.pending_transactions)
        self.pending_transactions = [tx for tx in self.pending_transactions if tx.txid not in txid_set]
        after_count = len(self.pending_transactions)
        cleared = before_count - after_count
        
        # Only log at INFO level if transactions were actually cleared
        if cleared > 0:
            logger.info(f"Cleared {cleared} processed transactions")
        else:
            logger.debug("No transactions needed clearing")
            
        return cleared
    
    def get_transaction_stats(self) -> Dict[str, Any]:
        """Get statistics about pending transactions.
        
        Returns:
            Dict[str, Any]: Statistics including count, total fees, etc.
        """
        # Periodically purge invalid transactions from the database
        try:
            # Run this periodically to clean up database from invalid transactions
            purged_count = db.purge_invalid_transactions()
            if purged_count > 0:
                logger.info(f"Purged {purged_count} invalid transactions from database")
        except Exception as e:
            logger.error(f"Error purging invalid transactions: {str(e)}")
        
        # Batch fetch all uncommitted transactions from the database and add them to pending at once
        try:
            # Fetch all uncommitted transactions (up to 1000 for safety)
            db_txs = db.fetch_uncommitted_transactions(1000)
            if db_txs:
                num_txs = len(db_txs)
                if num_txs > 0:
                    logger.debug(f"Found {num_txs} uncommitted transactions in database")
                    
                    # Create a set of existing transaction IDs for fast lookup
                    existing_txids = {ptx.txid for ptx in self.pending_transactions}
                    
                    # Batch add all new transactions at once
                    new_txs = [tx for tx in db_txs if tx.txid not in existing_txids]
                    if new_txs:
                        self.pending_transactions.extend(new_txs)
                        logger.info(f"Added {len(new_txs)} new transactions to the pending batch")
                        
                        # Log individual transactions only at debug level
                        for tx in new_txs:
                            logger.debug(f"Added to batch: {tx.txid[:8]}... from {tx.sender_address[:8]}...")
                    else:
                        logger.debug("All transactions already in pending list")
            else:
                logger.debug("No uncommitted transactions found in database")
        except Exception as e:
            logger.error(f"Error fetching transactions from database: {str(e)}")
            
        if not self.pending_transactions:
            logger.debug("No pending transactions in memory or database")
            return {
                "count": 0,
                "total_fees": 0,
                "avg_fee": 0,
                "oldest_timestamp": None
            }
        
        total_fees = sum(tx.fee for tx in self.pending_transactions)
        oldest_timestamp = min(tx.timestamp for tx in self.pending_transactions)
        
        # Convert timestamp to datetime for better readability
        oldest_dt = datetime.fromtimestamp(oldest_timestamp, timezone.utc)
        
        return {
            "count": len(self.pending_transactions),
            "total_fees": total_fees,
            "avg_fee": total_fees / len(self.pending_transactions),
            "oldest_timestamp": oldest_timestamp,
            "oldest_datetime": oldest_dt.isoformat()
        }
