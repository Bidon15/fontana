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
import sys
import os
from typing import Dict, Optional, Any, List

# Add pylestia submodule to Python path for imports
pylestia_path = os.path.join(os.path.dirname(__file__), 'pylestia')
if pylestia_path not in sys.path:
    sys.path.insert(0, pylestia_path)

# Now we can import from pylestia
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
        """Convert a namespace ID to bytes.

        Args:
            namespace_id: Namespace ID string in hex format

        Returns:
            bytes: Namespace ID as bytes
        """
        # Convert hex string to bytes - pylestia expects 8-byte namespaces
        try:
            return bytes.fromhex(namespace_id)
        except ValueError:
            # If not valid hex, use a hash of the string instead
            hash_obj = hashlib.sha256(namespace_id.encode())
            return hash_obj.digest()[:8]  # Use first 8 bytes of hash
    
    def _get_namespace_for_block(self, block_height: int) -> str:
        """Generate a unique namespace ID for a block.
        
        Args:
            block_height: Block height
            
        Returns:
            str: Namespace ID (hex)
        """
        # Create a deterministic namespace ID based on the block height and a secret
        hash_input = f"{block_height}:{self.namespace}".encode()
        namespace_bytes = hashlib.sha256(hash_input).digest()[:8]
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
            # Return None when disabled
            return None
        
        try:
            # Serialize block data to JSON
            block_data = block.model_dump_json().encode()
            
            # Generate namespace ID for this block
            namespace_id = self._get_namespace_for_block(block.header.height)
            namespace_bytes = self._namespace_id_bytes(namespace_id)
            
            # Create namespace and blob objects
            namespace = Namespace(namespace_bytes)
            blob = Blob(namespace=namespace, data=block_data)  # Add namespace parameter
            
            # Submit blob to Celestia
            response = self.client.blob.submit(
                namespace_id=namespace,  # Pass the namespace object
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
    
    def fetch_block_data(self, blob_ref: str) -> Optional[Block]:
        """Fetch block data from a blob reference.

        Args:
            blob_ref: Blob reference in format "height:namespace"

        Returns:
            Optional[Block]: The fetched block data, or None if not found
        """
        if not self.enabled:
            logger.info(f"Celestia disabled, skipping fetch for {blob_ref}")
            return None

        try:
            # Parse the blob reference
            height_str, namespace_id = blob_ref.split(":")
            height = int(height_str)
            
            # Create a namespace object
            namespace_bytes = self._namespace_id_bytes(namespace_id)
            namespace = Namespace(namespace_bytes)
            
            # Fetch blob data
            response = self.client.blob.get(
                height=height,
                namespace_id=namespace
            )
            
            if not response.data:
                logger.warning(f"No data found for blob {blob_ref}")
                return None
            
            # Extract and parse the block data
            return self._extract_blob_data(response.data)
            
        except Exception as e:
            logger.error(f"Error fetching blob data for reference {blob_ref}: {str(e)}")
            return None
    
    def _extract_blob_data(self, data: List[bytes]) -> Block:
        """Extract and parse block data from blob response.
        
        Args:
            data: Blob data from Celestia
            
        Returns:
            Block: The parsed block data
        """
        # The data comes as a list of byte arrays, but we expect just one item
        block_json = data[0].decode('utf-8')
        block_dict = json.loads(block_json)
        
        # Create a Block object from the dict
        return Block.model_validate(block_dict)
    
    def check_confirmation(self, namespace_id: str) -> bool:
        """Check if a block submission is confirmed on Celestia.
        
        Args:
            namespace_id: Namespace ID of the submission to check
            
        Returns:
            bool: True if confirmed, False otherwise
        """
        if not self.enabled:
            logger.info(f"Celestia disabled, cannot check confirmation for {namespace_id}")
            return False
            
        # Check if we have a record of this submission
        if namespace_id not in self.pending_submissions:
            logger.warning(f"No pending submission found for namespace {namespace_id}")
            return False
            
        # Get submission details
        submission = self.pending_submissions[namespace_id]
        
        # If already confirmed, no need to check again
        if submission.get("confirmed", False):
            return True
            
        try:
            # Get the current height from Celestia
            celestia_height = submission["celestia_height"]
            
            # Create a namespace object
            namespace_bytes = self._namespace_id_bytes(namespace_id)
            namespace = Namespace(namespace_bytes)
            
            # Check if the blob is still available at the original height
            response = self.client.blob.get(
                height=celestia_height,
                namespace_id=namespace
            )
            
            # If we got data back, the blob is confirmed
            is_confirmed = len(response.data) > 0
            
            if is_confirmed:
                # Mark as confirmed and send notification
                submission["confirmed"] = True
                
                if self.notification_manager:
                    self.notification_manager.notify(
                        notification_type=NotificationType.BLOCK_CONFIRMED_ON_DA,
                        block_height=submission["block_height"]
                    )
                    
                logger.info(f"Block {submission['block_height']} confirmed on Celestia")
                
            return is_confirmed
            
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
