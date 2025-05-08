"""
Notification manager for the Fontana system.

This module provides a notification system for transaction and block events,
including rollup confirmations and Celestia DA commitments.
"""

import logging
import enum
import time
import threading
import asyncio
from typing import Dict, Set, List, Callable, Any, Optional, Awaitable
from datetime import datetime

from fontana.core.config import config

# Set up logging
logger = logging.getLogger(__name__)


class NotificationType(enum.Enum):
    """Types of notifications that can be subscribed to."""

    TRANSACTION_RECEIVED = "transaction_received"  # Transaction validated and accepted
    TRANSACTION_REJECTED = "transaction_rejected"  # Transaction failed validation
    BLOCK_CREATED = "block_created"  # New block created containing transactions
    TRANSACTION_INCLUDED = "transaction_included"  # Transaction included in a block
    CELESTIA_COMMITTED = (
        "celestia_committed"  # Block data committed to Celestia DA layer
    )
    BLOCK_SUBMITTED_TO_DA = "block_submitted_to_da"  # Block submitted to DA layer
    BLOCK_COMMITTED_TO_DA = (
        "block_committed_to_da"  # Block successfully committed to DA layer
    )
    BLOCK_CONFIRMED_ON_DA = "block_confirmed_on_da"  # Block confirmed on DA layer
    # Bridge-related notification types
    DEPOSIT_PROCESSED = "deposit_processed"  # Deposit from L1 processed successfully
    WITHDRAWAL_CONFIRMED = "withdrawal_confirmed"  # Withdrawal confirmation from L1


class NotificationManager:
    """
    Notification manager for the Fontana system.

    Handles subscriptions to various events and notifies subscribers
    when those events occur. Supports both synchronous callbacks
    and asynchronous webhook notifications.
    """

    def __init__(self):
        """Initialize the notification manager."""
        # Mapping of notification types to subscribers
        self.subscribers: Dict[NotificationType, Set[Callable]] = {
            event_type: set() for event_type in NotificationType
        }

        # Mapping of transaction IDs to interested subscribers
        self.tx_subscribers: Dict[str, Set[Callable]] = {}

        # Mapping of block heights to interested subscribers
        self.block_subscribers: Dict[int, Set[Callable]] = {}

        # Lock for thread safety
        self.lock = threading.RLock()

        # Async event loop for webhook callbacks
        self.loop = asyncio.new_event_loop()
        self.webhook_thread = threading.Thread(
            target=self._run_webhook_loop, daemon=True
        )
        self.webhook_thread.start()

        logger.info("Notification manager initialized")

    def _run_webhook_loop(self):
        """Run the asyncio event loop for webhook callbacks."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def subscribe(self, event_type: NotificationType, callback: Callable) -> None:
        """Subscribe to a specific event type.

        Args:
            event_type: Type of event to subscribe to
            callback: Function to call when event occurs
        """
        with self.lock:
            self.subscribers[event_type].add(callback)
        logger.debug(f"Subscribed to {event_type.value} events")

    def unsubscribe(self, event_type: NotificationType, callback: Callable) -> None:
        """Unsubscribe from a specific event type.

        Args:
            event_type: Type of event to unsubscribe from
            callback: Function to remove from subscribers
        """
        with self.lock:
            if callback in self.subscribers[event_type]:
                self.subscribers[event_type].remove(callback)
        logger.debug(f"Unsubscribed from {event_type.value} events")

    def subscribe_transaction(self, txid: str, callback: Callable) -> None:
        """Subscribe to events for a specific transaction.

        Args:
            txid: Transaction ID to subscribe to
            callback: Function to call when events occur for this transaction
        """
        with self.lock:
            if txid not in self.tx_subscribers:
                self.tx_subscribers[txid] = set()
            self.tx_subscribers[txid].add(callback)
        logger.debug(f"Subscribed to events for transaction {txid}")

    def subscribe_block(self, height: int, callback: Callable) -> None:
        """Subscribe to events for a specific block.

        Args:
            height: Block height to subscribe to
            callback: Function to call when events occur for this block
        """
        with self.lock:
            if height not in self.block_subscribers:
                self.block_subscribers[height] = set()
            self.block_subscribers[height].add(callback)
        logger.debug(f"Subscribed to events for block at height {height}")

    def notify(self, event_type: NotificationType, data: Dict[str, Any]) -> None:
        """Notify all subscribers of an event.

        Args:
            event_type: Type of event that occurred
            data: Data associated with the event
        """
        # Add timestamp to the event data
        data["timestamp"] = datetime.now().isoformat()
        data["event_type"] = event_type.value

        # Notify subscribers to this event type
        self._notify_subscribers(self.subscribers.get(event_type, set()), data)

        # If this is a transaction event, notify transaction subscribers
        if "txid" in data and data["txid"] in self.tx_subscribers:
            txid = data["txid"]
            self._notify_subscribers(self.tx_subscribers.get(txid, set()), data)

            # If transaction is included in a block, clean up the subscription
            if event_type == NotificationType.TRANSACTION_INCLUDED:
                with self.lock:
                    self.tx_subscribers.pop(txid, None)

        # If this is a block event, notify block subscribers
        if "height" in data and data["height"] in self.block_subscribers:
            height = data["height"]
            self._notify_subscribers(self.block_subscribers.get(height, set()), data)

            # If block is committed to Celestia, clean up the subscription
            if event_type == NotificationType.CELESTIA_COMMITTED:
                with self.lock:
                    self.block_subscribers.pop(height, None)

        logger.debug(f"Notified subscribers of {event_type.value} event")

    def _notify_subscribers(
        self, subscribers: Set[Callable], data: Dict[str, Any]
    ) -> None:
        """Notify a set of subscribers with event data.

        Args:
            subscribers: Set of callback functions to notify
            data: Event data to pass to callbacks
        """
        for callback in subscribers:
            try:
                # Check if this is an async function or a regular one
                if asyncio.iscoroutinefunction(callback):
                    # Schedule async function on the event loop
                    asyncio.run_coroutine_threadsafe(callback(data), self.loop)
                else:
                    # Call synchronous function directly
                    callback(data)
            except Exception as e:
                logger.error(f"Error notifying subscriber: {str(e)}")

    def register_webhook(self, event_type: NotificationType, webhook_url: str) -> None:
        """Register a webhook for a specific event type.

        Args:
            event_type: Type of event to subscribe to
            webhook_url: URL to send POST requests to when event occurs
        """

        async def webhook_callback(data: Dict[str, Any]) -> None:
            """Async function to send webhook notification."""
            import aiohttp

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(webhook_url, json=data) as response:
                        if response.status >= 400:
                            logger.error(f"Webhook failed: {response.status}")
            except Exception as e:
                logger.error(f"Error sending webhook: {str(e)}")

        self.subscribe(event_type, webhook_callback)
        logger.info(f"Registered webhook for {event_type.value} events: {webhook_url}")


# Global notification manager instance
notification_manager = NotificationManager()
