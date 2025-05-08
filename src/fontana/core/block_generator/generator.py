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
        
        # Batch transaction detection and handling
        self.batch_mode_detected = False
        self.batch_start_time = None
        self.batch_collection_timeout = 3.0  # Wait 3 seconds after detecting first batch transaction
        
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
    
    def _sort_transactions_topologically(self, transactions: List[SignedTransaction]) -> List[SignedTransaction]:
        """Sort transactions topologically to ensure dependent transactions are processed in the right order.
        
        This is crucial for chained transactions in a batch - when one transaction's output is used as
        an input for another transaction in the same batch.
        
        Uses Kahn's algorithm for topological sorting (iterative, not recursive) to handle large batches.
        
        Args:
            transactions: List of transactions to sort
            
        Returns:
            Sorted list of transactions with dependencies resolved
        """
        if not transactions:
            return []
        
        # Create a map of transaction ID to transaction object for quick lookups
        tx_map = {tx.txid: tx for tx in transactions}
        
        # Create a set to track UTXOs created by transactions in this batch
        # Format: {"txid:output_index": "creating_txid"}
        batch_outputs = {}
        
        # First, identify all outputs created in this batch
        for tx in transactions:
            for i, output in enumerate(tx.outputs):
                utxo_ref = f"{tx.txid}:{i}"
                batch_outputs[utxo_ref] = tx.txid
        
        # Build the dependency graph and in-degree counts for each transaction
        # graph[txid1] = [txid2, txid3] means txid2 and txid3 depend on txid1
        # in_degree[txid] = number of transactions that txid depends on
        graph = {txid: [] for txid in tx_map}
        in_degree = {txid: 0 for txid in tx_map}
        
        # Calculate dependencies and in-degrees
        for tx in transactions:
            for inp in tx.inputs:
                utxo_ref = f"{inp.txid}:{inp.output_index}"
                if utxo_ref in batch_outputs:
                    # This transaction depends on another in the batch
                    creating_txid = batch_outputs[utxo_ref]
                    if creating_txid != tx.txid:  # Skip self-dependencies
                        # The current tx depends on creating_txid
                        graph[creating_txid].append(tx.txid)
                        in_degree[tx.txid] += 1
        
        # Kahn's algorithm for topological sort (iterative)
        # Start with all nodes that have no dependencies (in_degree == 0)
        queue = [txid for txid, degree in in_degree.items() if degree == 0]
        sorted_order = []
        
        # Process the queue
        while queue:
            # Get a transaction with no dependencies
            current = queue.pop(0)
            sorted_order.append(current)
            
            # For each transaction that depends on this one
            for dependent in graph[current]:
                # Reduce its in-degree (one fewer dependency)
                in_degree[dependent] -= 1
                # If it now has no dependencies, add to queue
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        # Check if we have a valid topological sort
        if len(sorted_order) != len(transactions):
            logger.warning(f"Topological sort could not resolve all dependencies. Possible cycle detected.")
            logger.warning(f"Falling back to original transaction order")
            return transactions
        
        # Convert the sorted txids back to transaction objects
        result = [tx_map[txid] for txid in sorted_order]
        
        # Log the result
        logger.info(f"Topologically sorted {len(result)} transactions for dependency resolution")
        if result != transactions and len(result) > 1:
            logger.info("Transaction order was changed to resolve dependencies")
            
        return result
    
    def generate_block(self) -> Optional[Block]:
        """Generate a new block from pending transactions.
        
        Returns:
            Optional[Block]: The generated block, or None if no transactions
        """
        try:
            logger.info("=== Attempting to generate a new block ===")
            # Get latest block from DB
            latest_block = db.get_latest_block()
            if latest_block:
                logger.info(f"Latest block: height={latest_block['height']}, hash={latest_block['hash']}")
                height = latest_block["height"] + 1
                prev_hash = latest_block["hash"]
            else:
                # Check if genesis block already exists in the database
                # This handles the case where get_latest_block might not find it
                # due to schema differences
                genesis_block = db.get_block_by_height(0)
                if genesis_block:
                    logger.info(f"Found genesis block: hash={genesis_block.header.hash}")
                    height = 1
                    prev_hash = genesis_block.header.hash
                else:
                    logger.info("No blocks in database yet, starting from genesis block")
                    height = 0
                    prev_hash = ""
            
            # Log block generation attempt
            logger.info(f"Attempting to generate block at height {height}")
            
            # Check DB directly for uncommitted transactions
            try:
                db_txs = db.fetch_uncommitted_transactions(1000)
                if db_txs:
                    logger.info(f"Found {len(db_txs)} uncommitted transactions in database check")
                    for tx in db_txs[:3]:  # Log a few for debugging
                        logger.info(f"DB TX: {tx.txid[:8]}... from {tx.sender_address[:8]}...")
            except Exception as e:
                logger.error(f"Error checking database transactions: {str(e)}")
            
            # Get pending transactions with transaction processor helper
            pending_txs = self.processor.get_pending_transactions(limit=self.max_block_size)
            
            # If there are no pending transactions, return None
            if not pending_txs:
                logger.info("No pending transactions available for processing, skipping block generation")
                return None
                
            # Log transactions we're including
            logger.info(f"Found {len(pending_txs)} pending transactions to include in block {height}")
            for i, tx in enumerate(pending_txs[:5]):  # Log first few
                logger.info(f"TX {i+1}: {tx.txid} from {tx.sender_address[:8]}...")
                logger.info(f"  - Inputs: {len(tx.inputs)}, Outputs: {len(tx.outputs)}, Fee: {tx.fee}")
                for j, inp in enumerate(tx.inputs[:2]):  # Log first few inputs
                    logger.info(f"  - Input {j+1}: {inp.txid[:8]}...:{inp.output_index}")
            
            # Sort transactions topologically if we have more than one transaction
            # This ensures that dependent transactions are processed in the right order
            if len(pending_txs) > 1:
                logger.info(f"Topologically sorting {len(pending_txs)} transactions to resolve dependencies")
                sorted_txs = self._sort_transactions_topologically(pending_txs)
            else:
                sorted_txs = pending_txs
            
            # Apply transactions to the ledger in the sorted order
            applied_txs = []
            applied_tx_ids = []
            
            # Log the transaction processing order if sorting changed it
            if sorted_txs != pending_txs and len(sorted_txs) > 1:
                logger.info("Processing transactions in dependency-based order:")
                for i, tx in enumerate(sorted_txs):
                    logger.info(f"  {i+1}. {tx.txid[:8]}...")
            
            for tx in sorted_txs:
                try:
                    # Apply transaction to update state
                    if self.ledger.apply_transaction(tx):
                        applied_txs.append(tx)
                        applied_tx_ids.append(tx.txid)
                        logger.debug(f"Successfully applied transaction {tx.txid[:8]}...")
                        
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
            try:
                # Use save_block instead of insert_block for consistency
                # save_block also handles marking transactions as committed
                db.save_block(block)
                
                # Clear processed transactions
                self.processor.clear_processed_transactions(applied_tx_ids)
            except Exception as e:
                logger.error(f"Error saving block {block.header.height} to database: {str(e)}")
                # We still want to continue with the rest of the process even if saving fails
            
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
                    celestia_namespace_id = self.celestia_client.post_block(block)
                    if celestia_namespace_id:
                        logger.info(f"Block {block.header.height} submitted to Celestia with namespace ID: {celestia_namespace_id}")
                except Exception as e:
                    # Log but don't fail - Celestia submissions can be retried
                    logger.error(f"Failed to submit block {block.header.height} to Celestia: {str(e)}")
            
            return block
            
        except Exception as e:
            logger.error(f"Error generating block: {str(e)}")
            raise BlockGenerationError(f"Failed to generate block: {str(e)}")
    
    def _is_batch_transaction(self, tx) -> bool:
        """Detect if a transaction is part of a batch based on its characteristics.
        
        We use heuristics like checking time proximity and sender addresses to determine this.
        
        Args:
            tx: The transaction to check
            
        Returns:
            bool: True if this transaction is likely part of a batch
        """
        # Look for the simplest characteristic first - multiple transactions from the same sender
        # in a short time period
        
        # Check the recent transactions from the same sender
        sender = tx.sender_address
        current_time = time.time()
        
        # If this is the first transaction we've seen from this sender in the last 5 seconds,
        # it might be the start of a batch
        recent_txs_from_sender = [t for t in self.processor.pending_transactions 
                                if t.sender_address == sender and 
                                   current_time - t.timestamp < 5]  # Within last 5 seconds
        
        # If we have more than one transaction from the same sender in the last 5 seconds,
        # it's probably part of a batch
        return len(recent_txs_from_sender) > 1
    
    def _block_generation_loop(self) -> None:
        """Main block generation loop for batched transaction processing.
        
        This loop runs every block_interval seconds (typically 5s) to batch transactions
        that have been immediately accepted by the CLI interface. This separation allows
        for sub-100ms CLI responses while efficiently batching transactions for Celestia.
        """
        logger.info(f"Fast transaction batching system started - CLI responds <100ms, batching every {self.block_interval}s")
        logger.info(f"Using max_block_size of {self.max_block_size} transactions per block")
        
        # Set initial last batch time
        self.last_batch_time = time.time()
        
        while self.is_running:
            try:
                # Check if it's time to generate a new block
                current_time = time.time()
                time_since_last_batch = current_time - self.last_batch_time
                
                # Get transaction stats from processor
                tx_stats = self.processor.get_transaction_stats()
                tx_count = tx_stats.get("count", 0)
                
                # Whether we should generate a block in this iteration
                should_generate = False
                
                # Check for potential batch transactions
                if tx_count > 0:
                    # Get a sample of the pending transactions to check for batch mode
                    sample_txs = self.processor.pending_transactions[:5]  # Check up to 5 transactions
                    
                    # If any transaction looks like it's part of a batch, set batch mode
                    for tx in sample_txs:
                        if self._is_batch_transaction(tx):
                            if not self.batch_mode_detected:
                                # First time detecting batch mode in this session
                                self.batch_mode_detected = True
                                self.batch_start_time = current_time
                                logger.info(f"🔍 Batch transaction pattern detected! Waiting for more transactions to accumulate")
                            break
                    
                    # If we're in batch mode and it hasn't expired yet, wait longer
                    if self.batch_mode_detected:
                        batch_wait_time = current_time - self.batch_start_time
                        if batch_wait_time < self.batch_collection_timeout:
                            logger.info(f"⏳ In batch collection mode, waiting for more transactions. Time elapsed: {batch_wait_time:.2f}s/{self.batch_collection_timeout:.2f}s")
                            # Sleep briefly and continue to next iteration to collect more transactions
                            time.sleep(0.2)
                            continue
                        else:
                            # Batch collection time is up, process whatever we have now
                            logger.info(f"⌛ Batch collection timeout reached after {batch_wait_time:.2f}s with {tx_count} transactions")
                            should_generate = True
                            # Reset batch mode
                            self.batch_mode_detected = False
                            self.batch_start_time = None
                
                # Standard block generation logic (when not in active batch collection)
                if not should_generate:
                    # Adjust these thresholds for better batching efficiency
                    min_tx_threshold = min(3, self.max_block_size // 10)  # At least 3 transactions to consider batching
                    min_force_batch_time = self.block_interval * 5      # Wait at least 5x interval before forcing a batch
                    ideal_batch_time = self.block_interval * 2          # Ideal time to wait for more transactions
                    
                    if tx_count >= self.max_block_size:
                        # We've reached the max block size, generate immediately
                        logger.info(f"Reached max block size ({tx_count} >= {self.max_block_size}), generating block now")
                        should_generate = True
                    elif tx_count >= min_tx_threshold and time_since_last_batch >= ideal_batch_time:
                        # We have a reasonable number of transactions and waited long enough to collect more
                        logger.info(f"Processing batch of {tx_count} transactions after waiting {time_since_last_batch:.2f}s for batching")
                        should_generate = True
                    elif tx_count > 0 and time_since_last_batch >= min_force_batch_time:
                        # Force generation only after waiting a significant time (5x interval)
                        # This gives time for more transactions to accumulate
                        logger.info(f"Forcing batch with {tx_count} transactions after {time_since_last_batch:.2f}s ({min_force_batch_time/self.block_interval}x interval)")
                        should_generate = True
                    else:
                        # If we're not generating a block, log the status so we can see it's waiting
                        if tx_count > 0:
                            logger.debug(f"Waiting for more transactions (current: {tx_count}, threshold: {min_tx_threshold}) or time ({time_since_last_batch:.2f}s / {min_force_batch_time}s)")
                        elif time_since_last_batch < self.block_interval:
                            logger.debug(f"Too soon since last batch ({time_since_last_batch:.2f}s < {self.block_interval}s), waiting...")
                        else:
                            logger.debug("No transactions and not enough time passed yet")
                
                if should_generate:
                    # Update last batch time
                    self.last_batch_time = current_time
                    
                    # Generate a block
                    logger.info("=== Attempting to generate a new block ===")
                    block = self.generate_block()
                    
                    if block:
                        # Log the block information for debugging
                        tx_count = len(block.transactions)
                        logger.info(f"Generated block {block.header.height} with {tx_count} transactions")
                        
                        # Submit block to data availability layer if available
                        applied_tx_ids = [tx.txid for tx in block.transactions]
                        
                        if self.celestia_client:
                            try:
                                # Submit to Celestia
                                blob_ref = self.celestia_client.post_block(block)
                                logger.info(f"Block {block.header.height} submitted to Celestia with namespace ID: {blob_ref}")
                                
                                # Update block with blob reference
                                db.update_block_blob_ref(block.header.height, blob_ref)
                                
                                # Note: Finality hash submission to Celestia is handled separately if needed
                                # No need to submit finality hash for basic functionality
                                
                            except Exception as e:
                                logger.error(f"Failed to submit block to Celestia: {str(e)}")
                        else:
                            logger.debug(f"No Celestia client available, skipping DA layer submission")
                            
                        # Always clear the processed transactions
                        self.processor.clear_processed_transactions(applied_tx_ids)
                    else:
                        logger.debug("No pending transactions to batch")
                
                # Sleep for a short period to avoid hammering the CPU
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in block generation loop: {str(e)}")
                # Don't wait as long on errors to avoid missing transactions
                time.sleep(1)
    
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
