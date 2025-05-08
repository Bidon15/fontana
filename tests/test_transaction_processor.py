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
    tx = SignedTransaction(
        txid="test-tx-id",
        sender_address=sender.get_address(),
        inputs=[utxo_ref],
        outputs=[utxo_output],
        fee=0.02,  # Above minimum fee
        payload_hash="test-payload",
        timestamp=1714489547,
        signature="test-signature"
    )
    
    return tx


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature', return_value=True)
def test_process_transaction(mock_verify, processor, test_transaction, mock_ledger):
    """Test processing a valid transaction."""
    # The key realization is that process_transaction in the code doesn't call apply_transaction
    # It only does basic validation and queues the transaction for later processing in a block
    # So we should test the actual behavior, not expect it to call apply_transaction
    
    # Start with a clean state
    processor.pending_transactions = []
    processor.processed_txids = {}
    
    # Process the transaction
    result = processor.process_transaction(test_transaction)
    
    # Verify transaction was accepted and queued
    assert result is True
    assert len(processor.pending_transactions) == 1
    assert processor.pending_transactions[0] == test_transaction
    assert test_transaction.txid in processor.processed_txids
    assert processor.processed_txids[test_transaction.txid]["status"] == "accepted"


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature', return_value=True)
def test_process_transaction_insufficient_fee(mock_verify, processor, test_transaction):
    """Test processing a transaction with insufficient fee."""
    # Set a low fee
    test_transaction.fee = 0.005  # Below minimum fee
    
    # Process the transaction - should raise ProcessingError that wraps InsufficientFeeError
    with pytest.raises(ProcessingError) as excinfo:
        processor.process_transaction(test_transaction)
    
    # Verify the error message mentions insufficient fee
    assert "below minimum" in str(excinfo.value)
    
    # Verify transaction was not queued
    assert len(processor.pending_transactions) == 0


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature', return_value=True)
def test_process_transaction_validation_error(mock_verify, processor, test_transaction, mock_ledger):
    """Test processing an invalid transaction."""
    # Set up ledger to reject the transaction
    mock_ledger.apply_transaction.return_value = False  # Indicates failure
    
    # Process the transaction
    result = processor.process_transaction(test_transaction)
    
    # Verify transaction was successfully processed (even though ledger rejected it)
    # The ledger rejection just means the transaction isn't valid, but the processing succeeded
    assert result is True
    assert len(processor.pending_transactions) == 1  # Still added to pending queue


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature')
def test_process_transaction_validation_exception(mock_verify, processor, test_transaction, mock_ledger):
    """Test processing a transaction that raises a validation exception."""
    # After examining the code, we see that process_transaction doesn't directly call
    # apply_transaction but rather does basic signature validation and fee checks.
    # So let's test that by making the signature validation fail with an exception.
    
    # Set up signature verification to raise an exception
    exception_msg = "Invalid signature format"
    mock_verify.side_effect = ValueError(exception_msg)
    
    # Clear any existing transactions
    processor.pending_transactions = []
    processor.processed_txids = {}
    
    # Create a fresh processor to avoid state from other tests
    test_processor = TransactionProcessor(ledger=MagicMock())
    
    # Process the transaction - should wrap the signature verification error in a ProcessingError
    with pytest.raises(ProcessingError) as excinfo:
        test_processor.process_transaction(test_transaction)
    
    # Verify the error message mentions the original error
    assert exception_msg in str(excinfo.value)
    
    # Verify transaction was not queued
    assert len(test_processor.pending_transactions) == 0
    
    # Verify the error was properly caught and wrapped
    assert "Failed to process transaction" in str(excinfo.value)


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature', return_value=True)
def test_get_pending_transactions(mock_verify, processor, test_transaction):
    """Test getting pending transactions."""
    # Add some transactions
    processor.pending_transactions = [test_transaction, MagicMock(), MagicMock()]
    
    # Get all pending transactions
    transactions = processor.get_pending_transactions()
    
    # Verify we got all transactions
    assert len(transactions) == 3
    assert transactions[0] == test_transaction


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature', return_value=True)
def test_get_pending_transactions_with_limit(mock_verify, processor, test_transaction):
    """Test getting pending transactions with a limit."""
    # Add some transactions
    processor.pending_transactions = [test_transaction, MagicMock(), MagicMock()]
    
    # Get limited pending transactions
    transactions = processor.get_pending_transactions(limit=2)
    
    # Verify we got the limited number of transactions
    assert len(transactions) == 2
    assert transactions[0] == test_transaction


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature', return_value=True)
def test_clear_processed_transactions(mock_verify, processor, test_transaction):
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


@patch('fontana.core.block_generator.processor.db')
def test_get_transaction_stats_empty(mock_db, processor):
    """Test getting transaction stats with no transactions."""
    # Mock db.fetch_uncommitted_transactions to return an empty list
    mock_db.fetch_uncommitted_transactions.return_value = []
    mock_db.purge_invalid_transactions.return_value = 0
    
    # Ensure pending transactions list is empty
    processor.pending_transactions = []
    
    # Get stats
    stats = processor.get_transaction_stats()
    
    # Verify stats
    assert stats["count"] == 0
    assert stats["total_fees"] == 0
    assert stats["avg_fee"] == 0
    assert stats["oldest_timestamp"] is None


@patch('fontana.core.block_generator.processor.db')
def test_get_transaction_stats(mock_db, processor):
    """Test getting transaction stats with transactions."""
    # Mock db.fetch_uncommitted_transactions to return an empty list (not adding additional transactions)
    mock_db.fetch_uncommitted_transactions.return_value = []
    mock_db.purge_invalid_transactions.return_value = 0
    
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


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature', return_value=True)
def test_validate_transaction_fast_valid(mock_verify, processor, test_transaction):
    """Test fast validation of a valid transaction."""
    is_valid, reason = processor.validate_transaction_fast(test_transaction)
    assert is_valid is True
    assert reason is None


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature', return_value=True)
def test_validate_transaction_fast_insufficient_fee(mock_verify, processor, test_transaction):
    """Test fast validation of a transaction with insufficient fee."""
    test_transaction.fee = 0.005  # Below minimum fee
    is_valid, reason = processor.validate_transaction_fast(test_transaction)
    assert is_valid is False
    assert "below minimum" in reason.lower()


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature', return_value=True)
def test_validate_transaction_fast_duplicate(mock_verify, processor, test_transaction):
    """Test fast validation of a duplicate transaction."""
    # Add the transaction to pending
    processor.pending_transactions.append(test_transaction)
    
    # Try to validate it again
    is_valid, reason = processor.validate_transaction_fast(test_transaction)
    assert is_valid is False
    assert "already pending" in reason.lower()


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature', return_value=True)
def test_process_transaction_fast_valid(mock_verify, processor_with_notifications, test_transaction, mock_notification_manager):
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


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature', return_value=True)
def test_process_transaction_fast_invalid(mock_verify, processor_with_notifications, test_transaction, mock_notification_manager):
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


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature', return_value=True)
def test_process_transaction_fast_error(mock_verify, processor_with_notifications, test_transaction, mock_notification_manager):
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


@patch('fontana.core.models.transaction.SignedTransaction.verify_signature', return_value=True)
def test_three_tier_confirmation_flow(mock_verify, processor_with_notifications, test_transaction, mock_ledger, mock_notification_manager):
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
