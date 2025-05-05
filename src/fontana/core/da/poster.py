"""
Blob Poster daemon for the Fontana system.

This module provides a daemon process that watches for new blocks
in the database and posts them to the Celestia Data Availability layer.
"""
import time
import logging
import threading
from typing import Optional, List, Dict, Any
import json

from fontana.core.config import config
from fontana.core.db import db
from fontana.core.models.block import Block
from fontana.core.da.client import CelestiaClient, CelestiaSubmissionError
from fontana.core.notifications import NotificationManager, NotificationType

# Set up logging
logger = logging.getLogger(__name__)


class BlobPoster:
    """
    Daemon for posting blocks to the Celestia Data Availability layer.
    
    This daemon watches for new blocks in the database and posts them
    to Celestia, updating the block status when the submission is successful.
    """
    
    def __init__(
        self,
        celestia_client: Optional[CelestiaClient] = None,
        notification_manager: Optional[NotificationManager] = None,
        poll_interval: int = 2,
        max_retries: int = 3,
        backoff_factor: float = 1.5
    ):
        """Initialize the Blob Poster daemon.
        
        Args:
            celestia_client: Optional Celestia client to use, creates a new one if None
            notification_manager: Optional notification manager for event notifications
            poll_interval: Seconds to wait between polling for new blocks
            max_retries: Maximum number of retries for failed submissions
            backoff_factor: Backoff multiplier for retry delays
        """
        self.celestia_client = celestia_client or CelestiaClient(notification_manager)
        self.notification_manager = notification_manager
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        
        self.is_running = False
        self.thread = None
        self.retry_queue: Dict[int, Dict[str, Any]] = {}
        
    def fetch_uncommitted_blocks(self) -> List[Block]:
        """Fetch uncommitted blocks from the database.
        
        Returns:
            List[Block]: List of uncommitted blocks
        """
        try:
            # Get blocks that have been created but not yet committed to Celestia
            conn = db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT json 
                FROM blocks 
                WHERE committed = 0
                ORDER BY height ASC
            """)
            
            blocks = []
            for row in cursor.fetchall():
                block_data = json.loads(row[0])
                blocks.append(Block.model_validate(block_data))
                
            return blocks
            
        except Exception as e:
            logger.error(f"Error fetching uncommitted blocks: {str(e)}")
            return []
        finally:
            if conn:
                conn.close()
    
    def mark_block_committed(self, height: int, blob_ref: str) -> bool:
        """Mark a block as committed in the database.
        
        Args:
            height: Block height
            blob_ref: Celestia blob reference
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            conn = db.get_connection()
            cursor = conn.cursor()
            
            # Update the block's committed status and blob_ref
            cursor.execute("""
                UPDATE blocks 
                SET committed = 1, blob_ref = ? 
                WHERE height = ?
            """, (blob_ref, height))
            
            conn.commit()
            
            # Send notification if a manager is available
            if self.notification_manager:
                self.notification_manager.notify(
                    notification_type=NotificationType.BLOCK_COMMITTED_TO_DA,
                    block_height=height
                )
            
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error marking block {height} as committed: {str(e)}")
            return False
        finally:
            if conn:
                conn.close()
    
    def post_block_to_celestia(self, block: Block) -> Optional[str]:
        """Post a block to Celestia with retry logic.
        
        Args:
            block: Block to post
            
        Returns:
            Optional[str]: Celestia blob reference if successful, None otherwise
        """
        retry_count = 0
        delay = self.poll_interval  # Initial delay same as poll interval
        
        while retry_count <= self.max_retries:
            try:
                logger.info(f"Posting block {block.header.height} to Celestia (attempt {retry_count + 1})")
                blob_ref = self.celestia_client.post_block(block)
                
                if blob_ref:
                    # Successfully posted to Celestia
                    logger.info(f"Block {block.header.height} posted to Celestia: {blob_ref}")
                    
                    # Remove from retry queue if it was there
                    self.retry_queue.pop(block.header.height, None)
                    
                    return blob_ref
                    
                # If we get here, something went wrong but didn't raise an exception
                logger.warning(f"Failed to post block {block.header.height} to Celestia, no blob reference")
                
            except CelestiaSubmissionError as e:
                logger.error(f"Error posting block {block.header.height} to Celestia: {str(e)}")
            
            # If we're here, we need to retry
            retry_count += 1
            
            if retry_count <= self.max_retries:
                # Calculate backoff delay
                delay = delay * self.backoff_factor
                logger.info(f"Retrying block {block.header.height} in {delay:.2f} seconds (attempt {retry_count + 1})")
                
                # Add to retry queue
                self.retry_queue[block.header.height] = {
                    "block": block,
                    "retry_at": time.time() + delay,
                    "retry_count": retry_count
                }
                
                # Only wait on the first try, otherwise we'll handle it in the main loop
                if retry_count == 1:
                    time.sleep(delay)
            else:
                logger.error(f"Max retries reached for block {block.header.height}, will try again later")
                # Keep in retry queue for next cycle
                self.retry_queue[block.header.height] = {
                    "block": block,
                    "retry_at": time.time() + (delay * 2),  # Longer delay after max retries
                    "retry_count": 0  # Reset retry count for next cycle
                }
        
        return None
    
    def process_block(self, block: Block) -> bool:
        """Process a single uncommitted block.
        
        Args:
            block: Block to process
            
        Returns:
            bool: True if the block was successfully processed
        """
        # Log basic block info
        logger.info(f"Processing block {block.header.height} with {block.header.tx_count} transactions")
        
        # Post to Celestia
        blob_ref = self.post_block_to_celestia(block)
        
        if not blob_ref:
            logger.warning(f"Failed to post block {block.header.height} to Celestia")
            return False
        
        # Mark as committed in database
        success = self.mark_block_committed(block.header.height, blob_ref)
        
        if success:
            logger.info(f"Block {block.header.height} marked as committed with blob_ref {blob_ref}")
        else:
            logger.error(f"Failed to mark block {block.header.height} as committed in database")
        
        return success
    
    def process_retry_queue(self) -> None:
        """Process blocks in the retry queue that are ready for retry."""
        current_time = time.time()
        
        # Find items ready for retry
        ready_heights = [
            height for height, item in self.retry_queue.items() 
            if item["retry_at"] <= current_time
        ]
        
        # Process ready items
        for height in ready_heights:
            item = self.retry_queue[height]
            logger.info(f"Retrying block {height} from retry queue")
            
            success = self.process_block(item["block"])
            
            if success:
                # Remove from retry queue
                self.retry_queue.pop(height, None)
    
    def run(self) -> None:
        """Main loop for the Blob Poster daemon."""
        logger.info("Starting Blob Poster daemon")
        
        while self.is_running:
            try:
                # First process any blocks in the retry queue
                self.process_retry_queue()
                
                # Fetch uncommitted blocks
                blocks = self.fetch_uncommitted_blocks()
                
                if blocks:
                    logger.info(f"Found {len(blocks)} uncommitted blocks")
                    
                    # Process each block
                    for block in blocks:
                        # Skip blocks already in retry queue
                        if block.header.height in self.retry_queue:
                            continue
                            
                        self.process_block(block)
                
                # Wait before next poll
                time.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Error in Blob Poster daemon: {str(e)}")
                time.sleep(self.poll_interval * 2)  # Longer delay on error
    
    def start(self) -> None:
        """Start the Blob Poster daemon."""
        if self.is_running:
            logger.warning("Blob Poster daemon is already running")
            return
            
        self.is_running = True
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        
        # Start Celestia client monitor
        self.celestia_client.start_monitor()
        
        logger.info("Blob Poster daemon started")
    
    def stop(self) -> None:
        """Stop the Blob Poster daemon."""
        if not self.is_running:
            logger.warning("Blob Poster daemon is not running")
            return
            
        self.is_running = False
        
        # Stop Celestia client monitor
        self.celestia_client.stop_monitor()
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5.0)
            
        logger.info("Blob Poster daemon stopped")
