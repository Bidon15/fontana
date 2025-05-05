"""
Transaction processor for the Fontana system.

This module provides functionality for processing transactions directly,
checking fee requirements, and preparing them for inclusion in blocks.
"""
import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timezone

from fontana.core.config import config
from fontana.core.models.transaction import SignedTransaction
from fontana.core.ledger import Ledger, TransactionValidationError
from fontana.core.notifications import NotificationManager, NotificationType

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
        self.minimum_fee = config.minimum_transaction_fee
        logger.info(f"Transaction processor initialized with minimum fee={self.minimum_fee}")
    
    def process_transaction(self, tx: SignedTransaction) -> bool:
        """Process a transaction and queue it for inclusion in a block if valid.
        
        Args:
            tx: Transaction to process
            
        Returns:
            bool: True if the transaction was processed successfully
            
        Raises:
            InsufficientFeeError: If the transaction fee is below the minimum
            ProcessingError: If there's an error during processing
            TransactionValidationError: If the transaction is invalid
        """
        try:
            # Check minimum fee requirement
            if tx.fee < self.minimum_fee:
                raise InsufficientFeeError(
                    f"Transaction fee {tx.fee} is below minimum {self.minimum_fee}"
                )
            
            # Validate transaction (this checks signature, inputs, etc.)
            # But doesn't apply it to the state yet
            if not self.ledger.apply_transaction(tx):
                logger.warning(f"Transaction {tx.txid} failed validation")
                return False
            
            # Queue transaction for inclusion in next block
            self.pending_transactions.append(tx)
            logger.info(f"Transaction {tx.txid} processed successfully")
            return True
            
        except TransactionValidationError as e:
            logger.warning(f"Invalid transaction {tx.txid}: {str(e)}")
            raise
        except InsufficientFeeError:
            logger.warning(f"Transaction {tx.txid} has insufficient fee")
            raise
        except Exception as e:
            logger.error(f"Error processing transaction {tx.txid}: {str(e)}")
            raise ProcessingError(f"Failed to process transaction: {str(e)}")
    
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
        
        Args:
            limit: Maximum number of transactions to return
            
        Returns:
            List[SignedTransaction]: List of pending transactions
        """
        if limit is None or limit >= len(self.pending_transactions):
            return self.pending_transactions.copy()
        return self.pending_transactions[:limit]
    
    def clear_processed_transactions(self, txids: List[str]) -> None:
        """Remove processed transactions from the pending list.
        
        Args:
            txids: List of transaction IDs that have been included in a block
        """
        # Create a set for O(1) lookups
        txid_set = set(txids)
        
        # Filter out processed transactions
        self.pending_transactions = [
            tx for tx in self.pending_transactions if tx.txid not in txid_set
        ]
        
        logger.info(f"Cleared {len(txid_set)} processed transactions")
    
    def get_transaction_stats(self) -> Dict[str, Any]:
        """Get statistics about pending transactions.
        
        Returns:
            Dict[str, Any]: Statistics including count, total fees, etc.
        """
        if not self.pending_transactions:
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
