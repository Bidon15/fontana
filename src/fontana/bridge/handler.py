"""
Bridge handler interface for Fontana.

This module provides functions for handling L1 events like deposits and withdrawals,
connecting external components (like the vault watcher or Rust bridge) to the core ledger.
"""

import logging
from typing import Dict, Any, Optional, List, Callable

from fontana.core.ledger.ledger import Ledger
from fontana.core.notifications.manager import notification_manager
from fontana.core.notifications import NotificationType

# Set up logger
logger = logging.getLogger(__name__)


def handle_deposit_received(deposit_details: Dict[str, Any], ledger: Ledger) -> bool:
    """
    Handle deposit received from L1.
    
    This function processes the deposit details and forwards them to the ledger.
    It returns a boolean indicating whether the processing was successful.
    
    Args:
        deposit_details: Details of the deposit, including:
            - l1_tx_hash: Transaction hash on L1
            - recipient_address: Recipient address on the rollup
            - amount: Amount deposited
            - l1_block_height: Block height on L1
            - l1_block_time: Block timestamp on L1
        ledger: The ledger instance to process the deposit
        
    Returns:
        bool: True if deposit was processed successfully, False otherwise
    """
    # Log deposit details
    logger.info(f"Processing deposit: {deposit_details}")
    
    # Validate required fields
    required_fields = ["l1_tx_hash", "recipient_address", "amount", "l1_block_height"]
    for field in required_fields:
        if field not in deposit_details:
            logger.error(f"Missing required field in deposit: {field}")
            return False
    
    # Process deposit in ledger
    try:
        result = ledger.process_deposit_event(deposit_details)
        
        if result:
            # Send notification
            try:
                # Create notification data
                notification_data = {
                    "tx_hash": deposit_details["l1_tx_hash"],
                    "recipient": deposit_details["recipient_address"],
                    "amount": deposit_details["amount"]
                }
                
                # Send the notification
                notification_manager.notify(
                    event_type=NotificationType.DEPOSIT_PROCESSED,
                    data=notification_data
                )
            except Exception as e:
                # Log but don't fail if notification fails
                logger.error(f"Error processing deposit: {str(e)}")
        
        return result
    except Exception as e:
        logger.error(f"Error processing deposit: {str(e)}")
        return False


def handle_withdrawal_confirmed(withdrawal_details: Dict[str, Any], ledger: Ledger) -> bool:
    """
    Handle withdrawal confirmation from L1.
    
    This function processes withdrawal confirmation details and forwards them to the ledger.
    It returns a boolean indicating whether the processing was successful.
    
    Args:
        withdrawal_details: Details of the withdrawal, including:
            - l1_tx_hash: Transaction hash on L1
            - rollup_tx_hash: Corresponding transaction hash on the rollup
            - amount: Amount withdrawn
            - l1_block_height: Block height on L1 where confirmation occurred
        ledger: The ledger instance to process the withdrawal
        
    Returns:
        bool: True if withdrawal was processed successfully, False otherwise
    """
    # Log withdrawal details
    logger.info(f"Processing withdrawal confirmation: {withdrawal_details}")
    
    # Validate required fields
    required_fields = ["l1_tx_hash", "rollup_tx_hash", "amount", "l1_block_height"]
    for field in required_fields:
        if field not in withdrawal_details:
            logger.error(f"Missing required field in withdrawal: {field}")
            return False
    
    # Process withdrawal in ledger
    try:
        result = ledger.process_withdrawal_event(withdrawal_details)
        
        if result:
            # Send notification
            try:
                # Create notification data
                notification_data = {
                    "tx_hash": withdrawal_details["l1_tx_hash"],
                    "rollup_tx_hash": withdrawal_details["rollup_tx_hash"],
                    "amount": withdrawal_details["amount"]
                }
                
                # Send the notification
                notification_manager.notify(
                    event_type=NotificationType.WITHDRAWAL_CONFIRMED,
                    data=notification_data
                )
            except Exception as e:
                # Log but don't fail if notification fails
                logger.error(f"Error confirming withdrawal: {str(e)}")
        
        return result
    except Exception as e:
        logger.error(f"Error confirming withdrawal: {str(e)}")
        return False
