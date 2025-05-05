"""
Notification system for Fontana.

This module provides a notification system for the Fontana rollup,
allowing components to send and receive notifications for important events.
"""

import logging
from enum import Enum, auto
from typing import Dict, Any, Optional, List, Callable

# Set up logger
logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """Types of notifications that can be sent."""
    DEPOSIT_PROCESSED = auto()
    WITHDRAWAL_CONFIRMED = auto()
    BLOCK_CONFIRMED = auto()
    TRANSACTION_CONFIRMED = auto()
    ERROR = auto()


class NotificationManager:
    """
    Manager for sending and receiving notifications.
    
    This is a singleton class that allows components to register
    for specific notification types and receive callbacks when
    those notifications are triggered.
    """
    
    _instance = None
    
    @classmethod
    def get_instance(cls) -> 'NotificationManager':
        """
        Get the singleton instance of the notification manager.
        
        Returns:
            NotificationManager: The singleton instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """Initialize the notification manager."""
        # Make sure only one instance exists
        if self.__class__._instance is not None:
            raise RuntimeError("NotificationManager is a singleton - use get_instance()")
        
        self._subscribers = {}
        for notification_type in NotificationType:
            self._subscribers[notification_type] = []
    
    def subscribe(self, notification_type: NotificationType, callback: Callable) -> None:
        """
        Subscribe to a specific notification type.
        
        Args:
            notification_type: Type of notification to subscribe to
            callback: Function to call when the notification is triggered
        """
        if notification_type not in self._subscribers:
            self._subscribers[notification_type] = []
        
        self._subscribers[notification_type].append(callback)
        logger.debug(f"Subscribed to {notification_type.name}")
    
    def unsubscribe(self, notification_type: NotificationType, callback: Callable) -> None:
        """
        Unsubscribe from a specific notification type.
        
        Args:
            notification_type: Type of notification to unsubscribe from
            callback: Function that was previously subscribed
        """
        if notification_type in self._subscribers and callback in self._subscribers[notification_type]:
            self._subscribers[notification_type].remove(callback)
            logger.debug(f"Unsubscribed from {notification_type.name}")
    
    def notify(self, notification_type: NotificationType, **kwargs) -> None:
        """
        Send a notification to all subscribers.
        
        Args:
            notification_type: Type of notification to send
            **kwargs: Additional data to include with the notification
        """
        if notification_type not in self._subscribers:
            return
        
        logger.debug(f"Sending {notification_type.name} notification")
        for callback in self._subscribers[notification_type]:
            try:
                callback(notification_type=notification_type, **kwargs)
            except Exception as e:
                logger.error(f"Error in notification callback: {str(e)}")
