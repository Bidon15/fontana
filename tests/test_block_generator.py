"""
Tests for the block generator.
"""
import pytest
import time
from unittest.mock import patch, MagicMock, call

from fontana.core.models.transaction import SignedTransaction
from fontana.core.models.block import Block, BlockHeader
from fontana.core.ledger import Ledger
from fontana.core.block_generator.processor import TransactionProcessor
from fontana.core.block_generator.generator import BlockGenerator, BlockGenerationError


@pytest.fixture
def mock_ledger():
    """Create a mock ledger for testing."""
    ledger = MagicMock(spec=Ledger)
    ledger.apply_transaction.return_value = True
    ledger.get_current_state_root.return_value = "test-state-root"
    return ledger


@pytest.fixture
def mock_processor():
    """Create a mock transaction processor for testing."""
    processor = MagicMock(spec=TransactionProcessor)
    
    # Create mock transactions
    tx1 = MagicMock(spec=SignedTransaction, txid="tx1")
    tx2 = MagicMock(spec=SignedTransaction, txid="tx2")
    tx3 = MagicMock(spec=SignedTransaction, txid="tx3")
    
    # Set up processor methods
    processor.get_pending_transactions.return_value = [tx1, tx2, tx3]
    
    return processor


@pytest.fixture
def mock_db():
    """Create a mock DB for testing."""
    with patch("fontana.core.block_generator.generator.db") as mock_db:
        # Set up default mock behaviors
        mock_db.get_latest_block.return_value = {
            "height": 10,
            "hash": "previous-block-hash"
        }
        yield mock_db


@pytest.fixture
def block_generator(mock_ledger, mock_processor):
    """Create a BlockGenerator instance for testing."""
    with patch("fontana.core.block_generator.generator.config") as mock_config:
        # Set up config values
        mock_config.block_interval_seconds = 5
        mock_config.max_block_transactions = 100
        mock_config.fee_schedule_id = "test-fee-schedule"
        
        return BlockGenerator(
            ledger=mock_ledger,
            processor=mock_processor
        )


def test_block_generator_init(mock_ledger, mock_processor):
    """Test BlockGenerator initialization."""
    with patch("fontana.core.block_generator.generator.config") as mock_config:
        # Set up config values
        mock_config.block_interval_seconds = 5
        mock_config.max_block_transactions = 100
        mock_config.fee_schedule_id = "test-fee-schedule"
        
        generator = BlockGenerator(
            ledger=mock_ledger,
            processor=mock_processor
        )
        
        assert generator.ledger == mock_ledger
        assert generator.processor == mock_processor
        assert generator.is_running is False
        assert generator.block_interval == 5
        assert generator.max_block_size == 100


@patch("fontana.core.block_generator.generator.time")
@patch("fontana.core.block_generator.generator.config")
def test_create_block_header(mock_config, mock_time, block_generator):
    """Test creating a block header."""
    # Set up time mock
    current_time = 1714489547
    mock_time.time.return_value = current_time
    
    # Set up config mock
    mock_config.fee_schedule_id = "test-fee-schedule"
    
    # Create mock transactions
    transactions = [MagicMock(), MagicMock()]
    
    # Create a block header
    header = block_generator.create_block_header(
        height=5,
        prev_hash="prev-hash",
        state_root="state-root",
        transactions=transactions
    )
    
    # Verify header properties
    assert header.height == 5
    assert header.prev_hash == "prev-hash"
    assert header.state_root == "state-root"
    assert header.timestamp == current_time
    assert header.tx_count == 2
    assert header.fee_schedule_id == "test-fee-schedule"
    assert header.hash is not None  # Hash should be generated


def test_generate_block(block_generator, mock_ledger, mock_processor, mock_db):
    """Test generating a block from pending transactions."""
    # Generate a block
    block = block_generator.generate_block()
    
    # Verify block properties
    assert isinstance(block, Block)
    assert block.header.height == 11  # 10 + 1
    assert block.header.prev_hash == "previous-block-hash"
    assert block.header.state_root == "test-state-root"
    assert len(block.transactions) == 3
    
    # Verify interactions with ledger and processor
    assert mock_ledger.apply_transaction.call_count == 3
    mock_processor.get_pending_transactions.assert_called_once()
    mock_processor.clear_processed_transactions.assert_called_once_with(["tx1", "tx2", "tx3"])
    mock_db.insert_block.assert_called_once()


def test_generate_block_no_transactions(block_generator, mock_processor):
    """Test generating a block with no pending transactions."""
    # Set up processor to return empty list
    mock_processor.get_pending_transactions.return_value = []
    
    # Generate a block
    block = block_generator.generate_block()
    
    # Verify no block was generated
    assert block is None


def test_generate_block_failed_transactions(block_generator, mock_ledger, mock_processor):
    """Test generating a block with transactions that fail to apply."""
    # Set up ledger to reject all transactions
    mock_ledger.apply_transaction.return_value = False
    
    # Generate a block
    block = block_generator.generate_block()
    
    # Verify no block was generated
    assert block is None


@patch("fontana.core.block_generator.generator.threading.Thread")
def test_start_stop(mock_thread, block_generator):
    """Test starting and stopping the block generator."""
    # Start the generator
    block_generator.start()
    
    # Verify thread was started
    assert mock_thread.called
    assert block_generator.is_running is True
    
    # Stop the generator
    block_generator.stop()
    
    # Verify generator is stopped
    assert block_generator.is_running is False


@patch("fontana.core.block_generator.generator.time")
def test_block_generation_loop(mock_time, block_generator):
    """Test the block generation loop behavior."""
    # Mock generator methods
    block_generator.generate_block = MagicMock()
    
    # Set up time.sleep to raise an exception after the first call
    # to break out of the loop
    mock_time.sleep.side_effect = [None, Exception("Stop loop")]
    
    # Set running flag
    block_generator.is_running = True
    
    # Run the loop (will exit after second sleep call)
    try:
        block_generator._block_generation_loop()
    except Exception:
        pass
    
    # Verify block was generated and sleep was called with the correct interval
    block_generator.generate_block.assert_called()
    mock_time.sleep.assert_called_with(5)  # Updated to match our new default of 5 seconds
