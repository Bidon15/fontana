"""
Tests for the bridge handler interface.
"""
import pytest
from unittest.mock import MagicMock, patch, ANY

from fontana.bridge.handler import handle_deposit_received, handle_withdrawal_confirmed
from fontana.core.ledger.ledger import Ledger
from fontana.core.notifications import NotificationType


@pytest.fixture
def mock_ledger():
    """Create a mock ledger."""
    ledger = MagicMock(spec=Ledger)
    ledger.process_deposit_event.return_value = True
    ledger.process_withdrawal_event.return_value = True
    return ledger


@pytest.fixture
def mock_notification_manager():
    """Create a mock notification manager."""
    with patch('fontana.bridge.handler.notification_manager') as mock_nm:
        yield mock_nm


class TestBridgeHandler:
    """Tests for the bridge handler interface."""
    
    def test_handle_deposit_received_success(self, mock_ledger, mock_notification_manager):
        """Test successful deposit handling."""
        # Set up mock ledger to return success
        mock_ledger.process_deposit_event.return_value = True
        
        # Test data
        deposit = {
            "l1_tx_hash": "test_tx_123",
            "recipient_address": "fontana1abc123def456",
            "amount": 10.0,
            "l1_block_height": 1000,
            "l1_block_time": 1714489547
        }
        
        # Call function
        result = handle_deposit_received(deposit, mock_ledger)
        
        # Verify ledger was called with the right parameters
        mock_ledger.process_deposit_event.assert_called_once_with(deposit)
        
        # Verify notification was sent
        mock_notification_manager.notify.assert_called_once_with(
            event_type=NotificationType.DEPOSIT_PROCESSED,
            data={
                "tx_hash": "test_tx_123",
                "recipient": "fontana1abc123def456",
                "amount": 10.0
            }
        )
        
        # Verify result
        assert result is True
    
    def test_handle_deposit_received_missing_field(self, mock_ledger, mock_notification_manager):
        """Test deposit handling with missing field."""
        # Test data with missing field
        deposit = {
            "l1_tx_hash": "test_tx_123",
            # Missing recipient_address
            "amount": 10.0,
            "l1_block_height": 1000
        }
        
        # Call function
        result = handle_deposit_received(deposit, mock_ledger)
        
        # Verify ledger was not called
        mock_ledger.process_deposit_event.assert_not_called()
        
        # Verify result
        assert result is False
    
    def test_handle_deposit_received_ledger_failure(self, mock_ledger, mock_notification_manager):
        """Test deposit handling with ledger failure."""
        # Set up mock ledger to return failure
        mock_ledger.process_deposit_event.return_value = False
        
        # Test data
        deposit = {
            "l1_tx_hash": "test_tx_123",
            "recipient_address": "fontana1abc123def456",
            "amount": 10.0,
            "l1_block_height": 1000,
            "l1_block_time": 1714489547
        }
        
        # Call function
        result = handle_deposit_received(deposit, mock_ledger)
        
        # Verify ledger was called
        mock_ledger.process_deposit_event.assert_called_once_with(deposit)
        
        # Verify notification was not sent
        mock_notification_manager.notify.assert_not_called()
        
        # Verify result
        assert result is False
    
    def test_handle_withdrawal_confirmed_success(self, mock_ledger, mock_notification_manager):
        """Test successful withdrawal confirmation."""
        # Set up mock ledger to return success
        mock_ledger.process_withdrawal_event.return_value = True
        
        # Test data
        withdrawal = {
            "l1_tx_hash": "test_tx_456",
            "rollup_tx_hash": "rollup_tx_789",
            "amount": 5.0,
            "l1_block_height": 1001
        }
        
        # Call function
        result = handle_withdrawal_confirmed(withdrawal, mock_ledger)
        
        # Verify ledger was called with the right parameters
        mock_ledger.process_withdrawal_event.assert_called_once_with(withdrawal)
        
        # Verify notification was sent
        mock_notification_manager.notify.assert_called_once_with(
            event_type=NotificationType.WITHDRAWAL_CONFIRMED,
            data={
                "tx_hash": "test_tx_456",
                "rollup_tx_hash": "rollup_tx_789",
                "amount": 5.0
            }
        )
        
        # Verify result
        assert result is True
    
    def test_handle_withdrawal_confirmed_missing_field(self, mock_ledger, mock_notification_manager):
        """Test withdrawal confirmation with missing field."""
        # Test data with missing field
        withdrawal = {
            "l1_tx_hash": "test_tx_456",
            # Missing rollup_tx_hash
            "amount": 5.0,
            "l1_block_height": 1001
        }
        
        # Call function
        result = handle_withdrawal_confirmed(withdrawal, mock_ledger)
        
        # Verify ledger was not called
        mock_ledger.process_withdrawal_event.assert_not_called()
        
        # Verify result
        assert result is False
    
    def test_handle_withdrawal_confirmed_ledger_failure(self, mock_ledger, mock_notification_manager):
        """Test withdrawal confirmation with ledger failure."""
        # Set up mock ledger to return failure
        mock_ledger.process_withdrawal_event.return_value = False
        
        # Test data
        withdrawal = {
            "l1_tx_hash": "test_tx_456",
            "rollup_tx_hash": "rollup_tx_789",
            "amount": 5.0,
            "l1_block_height": 1001
        }
        
        # Call function
        result = handle_withdrawal_confirmed(withdrawal, mock_ledger)
        
        # Verify ledger was called
        mock_ledger.process_withdrawal_event.assert_called_once_with(withdrawal)
        
        # Verify notification was not sent
        mock_notification_manager.notify.assert_not_called()
        
        # Verify result
        assert result is False
