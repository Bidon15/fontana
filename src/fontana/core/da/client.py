"""
Celestia client for the Fontana system.

This module provides a client for interacting with the Celestia Data Availability layer,
submitting block data, and monitoring for confirmations.
"""
import json
import time
import threading
import logging
import hashlib
from typing import Dict, Optional

from pylestia.node_api import Client
from pylestia.types import Namespace, Blob

from fontana.core.config import config
from fontana.core.models.block import Block
from fontana.core.notifications import NotificationManager, NotificationType

# Set up logging
logger = logging.getLogger(__name__)


class CelestiaSubmissionError(Exception):
    """Exception raised when submitting to Celestia fails."""
    pass


class CelestiaClient:
    """
    Client for interacting with the Celestia Data Availability layer.
    
    This client handles submitting block data to Celestia and monitoring
    for confirmations. It integrates with the notification system to
    provide updates on Celestia commitments.
    """
    
    def __init__(self, notification_manager: Optional[NotificationManager] = None):
        """Initialize the Celestia client.
        
        Args:
            notification_manager: Optional notification manager for event notifications
        """
        self.node_url = config.celestia_node_url
        self.auth_token = config.celestia_auth_token
        self.namespace = config.celestia_namespace or "fontana"
        self.notification_manager = notification_manager
        self.is_running = False
        self.monitor_thread = None
        self.client = Client(self.node_url, self.auth_token) if self.node_url and self.auth_token else None
        
        # Track submissions and confirmations
        self.pending_submissions: Dict[str, Dict[str, Any]] = {}
        
        # Check if we have Celestia configuration
        self.enabled = bool(self.node_url and self.auth_token)
        
        if not self.node_url or not self.auth_token:
            logger.warning("Celestia integration disabled: missing configuration")
            self.enabled = False
        else:
            logger.info(f"Celestia client initialized with namespace={self.namespace}")
    
    def _namespace_id_bytes(self, namespace_id: str) -> bytes:
        """Convert a hex namespace ID to bytes.
        
        Args:
            namespace_id: Hex-encoded namespace ID
            
        Returns:
            bytes: Namespace ID as bytes
        """
        # Convert hex string to bytes
        return bytes.fromhex(namespace_id)
    
    def _get_namespace_for_block(self, block_height: int) -> str:
        """Generate a unique namespace ID for a block.
        
        Args:
            block_height: Height of the block
            
        Returns:
            str: Hex-encoded namespace ID
        """
        # Create a unique namespace based on our base namespace and block height
        # In production, you might use a more sophisticated scheme
        namespace_bytes = hashlib.sha256(f"{self.namespace}:{block_height}".encode()).digest()[:8]
        return namespace_bytes.hex()
    
    def post_block(self, block: Block) -> Optional[str]:
        """Submit a block to the Celestia DA layer.
        
        Args:
            block: Block to submit
            
        Returns:
            Optional[str]: Celestia blob reference if successful, None if disabled
            
        Raises:
            CelestiaSubmissionError: If submission fails
        """
        if not self.enabled:
            logger.info(f"Celestia disabled, skipping submission for block {block.header.height}")
            # Return a mock blob reference in test mode
            return f"mock-blob-ref-{block.header.height}"
        
        try:
            # Serialize block data to JSON
            block_data = block.model_dump_json().encode()
            
            # Generate namespace ID for this block
            namespace_id = self._get_namespace_for_block(block.header.height)
            namespace_bytes = self._namespace_id_bytes(namespace_id)
            
            # Create namespace and blob objects
            namespace = Namespace(namespace_bytes)
            blob = Blob(block_data)
            
            # Submit blob to Celestia
            response = self.client.blob.submit(
                namespace_id=namespace,
                data=blob,
                gas_limit=100000,  # Adjust based on blob size
                fee=2000           # Adjust based on network conditions
            )
            
            # Extract blob reference (height + namespace + commitment)
            blob_ref = f"{response.height}:{namespace_id}"
            
            # Track submission for monitoring
            self.pending_submissions[namespace_id] = {
                "block_height": block.header.height,
                "block_hash": block.header.hash,
                "submitted_at": time.time(),
                "celestia_height": response.height,
                "blob_ref": blob_ref,
                "confirmed": False
            }
            
            logger.info(f"Block {block.header.height} submitted to Celestia: blob_ref={blob_ref}")
            return blob_ref
            
        except Exception as e:
            logger.error(f"Error submitting block {block.header.height} to Celestia: {str(e)}")
            raise CelestiaSubmissionError(f"Failed to submit block: {str(e)}")
    
    def fetch_block_data(self, blob_ref: str) -> Optional[Dict[str, Any]]:
        """Fetch block data from Celestia using a blob reference.
        
        Args:
            blob_ref: Blob reference in format "height:namespace_id"
            
        Returns:
            Optional[Dict[str, Any]]: Deserialized block data or None if not found
        """
        if not self.enabled:
            logger.info(f"Celestia disabled, cannot fetch blob: {blob_ref}")
            return None
        
        try:
            # Parse blob reference
            parts = blob_ref.split(":")
            if len(parts) != 2:
                raise ValueError(f"Invalid blob reference format: {blob_ref}")
                
            height = int(parts[0])
            namespace_id = parts[1]
            namespace_bytes = self._namespace_id_bytes(namespace_id)
            
            # Create namespace object
            namespace = Namespace(namespace_bytes)
            
            # Fetch blob from Celestia
            response = self.client.blob.get(
                height=height,
                namespace_id=namespace
            )
            
            if not response.data:
                logger.warning(f"No blob data found for reference: {blob_ref}")
                return None
                
            # Decode and deserialize JSON data
            block_data = json.loads(response.data[0].decode())
            return block_data
            
        except Exception as e:
            logger.error(f"Error fetching blob data for reference {blob_ref}: {str(e)}")
            return None
    
    def check_confirmation(self, namespace_id: str) -> bool:
        """Check if a block submission is confirmed on Celestia.
        
        Args:
            namespace_id: Celestia namespace ID to check
            
        Returns:
            bool: True if confirmed, False otherwise
        """
        if not self.enabled:
            # Auto-confirm in mock mode after a delay
            submission = self.pending_submissions.get(namespace_id)
            if submission and not submission.get("confirmed"):
                elapsed = time.time() - submission.get("submitted_at", 0)
                if elapsed > 5:  # Mock 5-second confirmation time
                    submission["confirmed"] = True
                    return True
            return submission.get("confirmed", False) if submission else False
            
        try:
            # Check if the namespace exists at the expected height
            submission = self.pending_submissions.get(namespace_id)
            if not submission:
                return False
                
            celestia_height = submission.get("celestia_height")
            if not celestia_height:
                return False
                
            namespace_bytes = self._namespace_id_bytes(namespace_id)
            namespace = Namespace(namespace_bytes)
            
            # Check if blob exists
            response = self.client.blob.get(
                height=celestia_height,
                namespace_id=namespace
            )
            
            confirmed = len(response.data) > 0
            
            if confirmed and not submission.get("confirmed"):
                submission["confirmed"] = True
                block_height = submission.get("block_height")
                
                # Send notification if a notification manager is available
                if self.notification_manager and block_height:
                    self.notification_manager.notify(
                        notification_type=NotificationType.BLOCK_COMMITTED_TO_DA,
                        block_height=block_height
                    )
            
            return confirmed
            
        except Exception as e:
            logger.error(f"Error checking confirmation for namespace {namespace_id}: {str(e)}")
            return False
    
    def _monitor_pending_submissions(self):
        """Monitor pending submissions for confirmations."""
        while self.is_running:
            try:
                # Check all pending submissions
                for namespace_id, submission in list(self.pending_submissions.items()):
                    if not submission.get("confirmed"):
                        if self.check_confirmation(namespace_id):
                            logger.info(f"Block {submission.get('block_height')} confirmed on Celestia")
                
                # Sleep before checking again
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Error in Celestia monitor thread: {str(e)}")
                time.sleep(30)  # Back off on error
    
    def start_monitor(self):
        """Start the Celestia confirmation monitor."""
        if self.is_running:
            return
            
        self.is_running = True
        
        self.monitor_thread = threading.Thread(
            target=self._monitor_pending_submissions,
            daemon=True
        )
        self.monitor_thread.start()
        logger.info("Celestia confirmation monitor started")
    
    def stop_monitor(self):
        """Stop the Celestia confirmation monitor."""
        if not self.is_running:
            return
            
        self.is_running = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
            
        logger.info("Celestia confirmation monitor stopped")
