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
import asyncio
import base64
from typing import Dict, Optional, Any, List

# Add pylestia submodule to Python path for imports
pylestia_path = os.path.join(os.path.dirname(__file__), "pylestia")
if pylestia_path not in sys.path:
    sys.path.insert(0, pylestia_path)

# Now we can import from pylestia
from pylestia.node_api import Client, BlobAPI
from pylestia.node_api.rpc import JsonRpcClient
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

        # Initialize PyLestia client
        if self.node_url:
            # Create a single client instance with public interface
            self.client = Client(self.node_url)
            # Set initialized flag
            self.is_initialized = True
        else:
            self.client = None
            self.is_initialized = False

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
        # Ensure namespace_id is a valid 16-character (8-byte) hex string
        # This is required by Celestia and pylestia
        if len(namespace_id) != 16 or not all(
            c in "0123456789abcdefABCDEF" for c in namespace_id
        ):
            # If not valid, normalize it to a 16-character hex string
            hash_obj = hashlib.sha256(namespace_id.encode())
            normalized_namespace = hash_obj.hexdigest()[:16].lower()
            logger.info(
                f"Normalizing namespace '{namespace_id}' to '{normalized_namespace}'"
            )
            namespace_id = normalized_namespace

        # Convert the validated hex string to bytes
        return bytes.fromhex(namespace_id)

    def _get_namespace_for_block(self, block_height: int) -> str:
        """Get the namespace ID for a block.

        Args:
            block_height: Block height (not used with fixed namespace)

        Returns:
            str: Namespace ID (hex)
        """
        # Use the configured namespace directly instead of generating a unique one per block
        # This ensures all blocks are submitted to the same namespace

        # If we have a valid 16-character hex namespace from config, use it directly
        if (
            self.namespace
            and len(self.namespace) == 16
            and all(c in "0123456789abcdefABCDEF" for c in self.namespace)
        ):
            return self.namespace

        # If we don't have a valid namespace, generate a deterministic one from the namespace string
        # This will be the same for all blocks, but unique to this rollup instance
        hash_input = self.namespace.encode()
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
            logger.info(
                f"Celestia disabled, skipping submission for block {block.header.height}"
            )
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

            # Set up the async execution environment
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Reimplement using WebSockets protocol as shown in hello_world.py example
            async def submit_to_celestia():
                # Convert HTTP URL to WebSocket URL if needed
                node_url = self.node_url
                if node_url.startswith("http://"):
                    node_url = node_url.replace("http://", "ws://")
                elif node_url.startswith("https://"):
                    node_url = node_url.replace("https://", "wss://")
                elif not node_url.startswith(("ws://", "wss://")):
                    # Add ws:// prefix if no protocol specified
                    node_url = f"ws://{node_url}"

                # Use IP address instead of hostname to avoid DNS resolution issues
                if "localhost" in node_url:
                    node_url = node_url.replace("localhost", "127.0.0.1")

                logger.info(f"Connecting to Celestia using WebSockets at {node_url}")

                # Create a new client with the WebSocket URL (positional parameter)
                client = Client(node_url)

                # Use the proper async context manager pattern
                async with client.connect(self.auth_token) as api:
                    logger.info("Connected to Celestia node, submitting blob...")
                    # Submit the blob (positional parameter)
                    return await api.blob.submit(blob)

            # Run the async function
            response = loop.run_until_complete(submit_to_celestia())

            # Process the response
            height = response.height
            commitments = (
                response.commitments if hasattr(response, "commitments") else []
            )

            # Use the first commitment if available, otherwise use the namespace_id
            commitment = commitments[0] if commitments else namespace_id
            blob_ref = f"{height}:{namespace_id}"

            # Track this submission
            submission_record = {
                "height": height,
                "namespace": namespace_id,
                "commitment": str(commitment) if commitment else None,
                "block_height": block.header.height,
                "timestamp": int(time.time()),
                "status": "pending",
            }
            self.pending_submissions[blob_ref] = submission_record

            logger.info(
                f"Block {block.header.height} submitted to Celestia: blob_ref={blob_ref}"
            )
            return blob_ref

        except Exception as e:
            logger.error(
                f"Error submitting block {block.header.height} to Celestia: {str(e)}"
            )
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
            response = self.client.blob.get(height=height, namespace_id=namespace)

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
        block_json = data[0].decode("utf-8")
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
            logger.info(
                f"Celestia disabled, cannot check confirmation for {namespace_id}"
            )
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
                height=celestia_height, namespace_id=namespace
            )

            # If we got data back, the blob is confirmed
            is_confirmed = len(response.data) > 0

            if is_confirmed:
                # Mark as confirmed and send notification
                submission["confirmed"] = True

                if self.notification_manager:
                    self.notification_manager.notify(
                        notification_type=NotificationType.BLOCK_CONFIRMED_ON_DA,
                        block_height=submission["block_height"],
                    )

                logger.info(f"Block {submission['block_height']} confirmed on Celestia")

            return is_confirmed

        except Exception as e:
            logger.error(
                f"Error checking confirmation for namespace {namespace_id}: {str(e)}"
            )
            return False

    def _monitor_pending_submissions(self):
        """Monitor pending submissions for confirmations."""
        while self.is_running:
            try:
                # Check all pending submissions
                for namespace_id, submission in list(self.pending_submissions.items()):
                    if not submission.get("confirmed"):
                        if self.check_confirmation(namespace_id):
                            logger.info(
                                f"Block {submission.get('block_height')} confirmed on Celestia"
                            )

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
            target=self._monitor_pending_submissions, daemon=True
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
