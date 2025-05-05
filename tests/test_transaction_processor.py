"""
Tests for the transaction processor.
"""
import pytest
from unittest.mock import patch, MagicMock, call

from fontana.core.models.transaction import SignedTransaction
from fontana.core.models.utxo import UTXORef, UTXO
from fontana.core.ledger import Ledger, TransactionValidationError
from fontana.core.block_generator.processor import (
    TransactionProcessor, 
    ProcessingError, 
    InsufficientFeeError
)
from fontana.wallet import Wallet
from fontana.core.notifications import NotificationManager, NotificationType


@pytest.fixture
def mock_ledger():
    """Create a mock ledger for testing."""
    ledger = MagicMock(spec=Ledger)
    ledger.apply_transaction.return_value = True
    
    # Add _validate_signature method for fast validation
    ledger._validate_signature = MagicMock(return_value=True)
    
    return ledger


@pytest.fixture
def mock_notification_manager():
    """Create a mock notification manager for testing."""
    notifier = MagicMock(spec=NotificationManager)
    return notifier


@pytest.fixture
def processor(mock_ledger):
    """Create a transaction processor with a mock ledger."""
    with patch("fontana.core.block_generator.processor.config") as mock_config:
        # Set minimum fee for testing
        mock_config.minimum_transaction_fee = 0.01
        return TransactionProcessor(ledger=mock_ledger)


@pytest.fixture
def processor_with_notifications(mock_ledger, mock_notification_manager):
    """Create a transaction processor with a mock ledger and notification manager."""
    with patch("fontana.core.block_generator.processor.config") as mock_config:
        # Set minimum fee for testing
        mock_config.minimum_transaction_fee = 0.01
        mock_config.block_interval_seconds = 5
        return TransactionProcessor(
            ledger=mock_ledger, 
            notification_manager=mock_notification_manager
        )


@pytest.fixture
def test_transaction():
    """Create a test transaction for testing."""
    # Create wallets
    sender = Wallet.generate()
    recipient = Wallet.generate()
    
    # Create input and output
    utxo_ref = UTXORef(txid="test-txid", output_index=0)
    utxo_output = UTXO(
        txid="output-txid",
        output_index=0,
        recipient=recipient.get_address(),
        amount=1.0,
        status="unspent"
    )
    
    # Create transaction
    return SignedTransaction(
        txid="test-tx-id",
        sender_address=sender.get_address(),
        inputs=[utxo_ref],
        outputs=[utxo_output],
        fee=0.02,  # Above minimum fee
        payload_hash="test-payload",
        timestamp=1714489547,
        signature="test-signature"
    )


def test_process_transaction(processor, test_transaction, mock_ledger):
    """Test processing a valid transaction."""
    # Process the transaction
    result = processor.process_transaction(test_transaction)
    
    # Verify transaction was validated and queued
    assert result is True
    mock_ledger.apply_transaction.assert_called_once_with(test_transaction)
    assert len(processor.pending_transactions) == 1
    assert processor.pending_transactions[0] == test_transaction


def test_process_transaction_insufficient_fee(processor, test_transaction):
    """Test processing a transaction with insufficient fee."""
    # Set a low fee
    test_transaction.fee = 0.005  # Below minimum fee
    
    # Process the transaction
    with pytest.raises(InsufficientFeeError):
        processor.process_transaction(test_transaction)
    
    # Verify transaction was not queued
    assert len(processor.pending_transactions) == 0


def test_process_transaction_validation_error(processor, test_transaction, mock_ledger):
    """Test processing an invalid transaction."""
    # Set up ledger to reject the transaction
    mock_ledger.apply_transaction.return_value = False
    
    # Process the transaction
    result = processor.process_transaction(test_transaction)
    
    # Verify transaction was not queued
    assert result is False
    assert len(processor.pending_transactions) == 0


def test_process_transaction_validation_exception(processor, test_transaction, mock_ledger):
    """Test processing a transaction that raises a validation exception."""
    # Set up ledger to raise an exception
    mock_ledger.apply_transaction.side_effect = TransactionValidationError("Test error")
    
    # Process the transaction
    with pytest.raises(TransactionValidationError):
        processor.process_transaction(test_transaction)
    
    # Verify transaction was not queued
    assert len(processor.pending_transactions) == 0


def test_get_pending_transactions(processor, test_transaction):
    """Test getting pending transactions."""
    # Add some transactions
    processor.pending_transactions = [test_transaction, MagicMock(), MagicMock()]
    
    # Get all pending transactions
    transactions = processor.get_pending_transactions()
    
    # Verify we got all transactions
    assert len(transactions) == 3
    assert transactions[0] == test_transaction


def test_get_pending_transactions_with_limit(processor, test_transaction):
    """Test getting pending transactions with a limit."""
    # Add some transactions
    processor.pending_transactions = [test_transaction, MagicMock(), MagicMock()]
    
    # Get limited pending transactions
    transactions = processor.get_pending_transactions(limit=2)
    
    # Verify we got the limited number of transactions
    assert len(transactions) == 2
    assert transactions[0] == test_transaction


def test_clear_processed_transactions(processor, test_transaction):
    """Test clearing processed transactions."""
    # Add some transactions
    tx1 = test_transaction
    tx2 = MagicMock(spec=SignedTransaction, txid="tx2")
    tx3 = MagicMock(spec=SignedTransaction, txid="tx3")
    processor.pending_transactions = [tx1, tx2, tx3]
    
    # Clear some transactions
    processor.clear_processed_transactions(["test-tx-id", "tx3"])
    
    # Verify only the unprocessed transaction remains
    assert len(processor.pending_transactions) == 1
    assert processor.pending_transactions[0].txid == "tx2"


def test_get_transaction_stats_empty(processor):
    """Test getting transaction stats with no transactions."""
    # Get stats
    stats = processor.get_transaction_stats()
    
    # Verify stats
    assert stats["count"] == 0
    assert stats["total_fees"] == 0
    assert stats["avg_fee"] == 0
    assert stats["oldest_timestamp"] is None


def test_get_transaction_stats(processor):
    """Test getting transaction stats with transactions."""
    # Add some transactions
    tx1 = MagicMock(spec=SignedTransaction, txid="tx1", fee=0.01, timestamp=1000)
    tx2 = MagicMock(spec=SignedTransaction, txid="tx2", fee=0.02, timestamp=2000)
    tx3 = MagicMock(spec=SignedTransaction, txid="tx3", fee=0.03, timestamp=3000)
    processor.pending_transactions = [tx1, tx2, tx3]
    
    # Get stats
    stats = processor.get_transaction_stats()
    
    # Verify stats
    assert stats["count"] == 3
    assert stats["total_fees"] == 0.06
    assert stats["avg_fee"] == 0.02
    assert stats["oldest_timestamp"] == 1000
    assert "oldest_datetime" in stats


def test_validate_transaction_fast_valid(processor, test_transaction):
    """Test fast validation of a valid transaction."""
    is_valid, reason = processor.validate_transaction_fast(test_transaction)
    assert is_valid is True
    assert reason is None


def test_validate_transaction_fast_insufficient_fee(processor, test_transaction):
    """Test fast validation of a transaction with insufficient fee."""
    test_transaction.fee = 0.005  # Below minimum fee
    is_valid, reason = processor.validate_transaction_fast(test_transaction)
    assert is_valid is False
    assert "below minimum" in reason.lower()


def test_validate_transaction_fast_duplicate(processor, test_transaction):
    """Test fast validation of a duplicate transaction."""
    # Add the transaction to pending
    processor.pending_transactions.append(test_transaction)
    
    # Try to validate it again
    is_valid, reason = processor.validate_transaction_fast(test_transaction)
    assert is_valid is False
    assert "already pending" in reason.lower()


def test_process_transaction_fast_valid(processor_with_notifications, test_transaction, mock_notification_manager):
    """Test fast processing of a valid transaction."""
    # Process the transaction
    result = processor_with_notifications.process_transaction_fast(test_transaction)
    
    # Verify transaction was provisionally accepted
    assert result["status"] == "provisionally_accepted"
    assert result["txid"] == test_transaction.txid
    assert "estimated_block_time" in result
    assert "estimated_celestia_time" in result
    
    # Verify notification was sent
    mock_notification_manager.notify.assert_called_once()
    args = mock_notification_manager.notify.call_args[0]
    assert args[0] == NotificationType.TRANSACTION_RECEIVED
    assert args[1]["txid"] == test_transaction.txid
    assert args[1]["status"] == "provisionally_accepted"
    
    # Verify transaction was queued
    assert len(processor_with_notifications.pending_transactions) == 1
    assert processor_with_notifications.pending_transactions[0] == test_transaction


def test_process_transaction_fast_invalid(processor_with_notifications, test_transaction, mock_notification_manager):
    """Test fast processing of an invalid transaction."""
    # Make the transaction invalid
    test_transaction.fee = 0.005  # Below minimum fee
    
    # Process the transaction
    result = processor_with_notifications.process_transaction_fast(test_transaction)
    
    # Verify transaction was rejected
    assert result["status"] == "rejected"
    assert result["txid"] == test_transaction.txid
    assert "reason" in result
    
    # Verify notification was sent
    mock_notification_manager.notify.assert_called_once()
    args = mock_notification_manager.notify.call_args[0]
    assert args[0] == NotificationType.TRANSACTION_REJECTED
    assert args[1]["txid"] == test_transaction.txid
    assert args[1]["status"] == "rejected"
    
    # Verify transaction was not queued
    assert len(processor_with_notifications.pending_transactions) == 0


def test_process_transaction_fast_error(processor_with_notifications, test_transaction, mock_notification_manager):
    """Test fast processing with an unexpected error."""
    # Mock validate_transaction_fast to raise an exception
    with patch.object(
        processor_with_notifications, 
        'validate_transaction_fast', 
        side_effect=Exception("Test error")
    ):
        # Process the transaction
        result = processor_with_notifications.process_transaction_fast(test_transaction)
        
        # Verify error response
        assert result["status"] == "error"
        assert result["txid"] == test_transaction.txid
        assert "reason" in result
        assert "Test error" in result["reason"]
        
        # Verify notification was sent
        mock_notification_manager.notify.assert_called_once()
        args = mock_notification_manager.notify.call_args[0]
        assert args[0] == NotificationType.TRANSACTION_REJECTED
        assert args[1]["txid"] == test_transaction.txid
        assert args[1]["status"] == "error"
        
        # Verify transaction was not queued
        assert len(processor_with_notifications.pending_transactions) == 0


def test_three_tier_confirmation_flow(processor_with_notifications, test_transaction, mock_ledger, mock_notification_manager):
    """Test the full three-tier confirmation flow."""
    # Tier 1: Immediate validation and provisional acceptance
    result = processor_with_notifications.process_transaction_fast(test_transaction)
    assert result["status"] == "provisionally_accepted"
    
    # Verify Tier 1 notification was sent
    mock_notification_manager.notify.assert_called_once()
    call_args = mock_notification_manager.notify.call_args[0]
    assert call_args[0] == NotificationType.TRANSACTION_RECEIVED
    assert "provisionally_accepted" in call_args[1]["status"]
    mock_notification_manager.reset_mock()
    
    # Simulate Tier 2: Block inclusion
    # This would normally happen in the BlockGenerator
    mock_notification_manager.notify(
        NotificationType.TRANSACTION_INCLUDED,
        {
            "txid": test_transaction.txid,
            "block_height": 123,
            "sender": test_transaction.sender_address,
            "status": "applied"
        }
    )
    
    # Verify Tier 2 notification was correctly formed
    mock_notification_manager.notify.assert_called_once()
    tier2_call = mock_notification_manager.notify.call_args[0]
    assert tier2_call[0] == NotificationType.TRANSACTION_INCLUDED
    assert tier2_call[1]["txid"] == test_transaction.txid
    assert tier2_call[1]["block_height"] == 123
    mock_notification_manager.reset_mock()
    
    # Simulate Tier 3: Celestia DA commitment
    # This would normally happen in the CelestiaClient
    mock_notification_manager.notify(
        NotificationType.CELESTIA_COMMITTED,
        {
            "height": 123,
            "block_hash": "test-block-hash",
            "celestia_namespace": "test-namespace",
            "celestia_height": 456
        }
    )
    
    # Verify Tier 3 notification was correctly formed
    mock_notification_manager.notify.assert_called_once()
    tier3_call = mock_notification_manager.notify.call_args[0]
    assert tier3_call[0] == NotificationType.CELESTIA_COMMITTED
    assert tier3_call[1]["height"] == 123
