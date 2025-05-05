"""
Integration tests for the bridge interface and vault watcher.
"""
import pytest
import time
import tempfile
import sqlite3
import logging
from unittest.mock import MagicMock, patch, ANY

from fontana.bridge.handler import handle_deposit_received, handle_withdrawal_confirmed
from fontana.core.ledger.ledger import Ledger
from fontana.core.notifications import NotificationType, NotificationManager
from scripts.vault_watcher import VaultWatcher


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


@pytest.fixture
def temp_db_path():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix='.db') as f:
        yield f.name


@patch('scripts.vault_watcher.handle_deposit_received')
def test_deposit_flow_from_l1_to_ledger(mock_bridge_handler, mock_ledger, temp_db_path):
    """
    Test the full flow from L1 deposit detection to ledger processing.

    This test simulates:
    1. Vault watcher detecting a deposit on L1
    2. Recording the deposit in the database
    3. Handling the deposit through the bridge interface
    4. Processing the deposit in the ledger
    """
    # Set up the mock handler
    mock_bridge_handler.return_value = True
    
    # Set up the database
    with sqlite3.connect(temp_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS vault_deposits (
            l1_tx_hash TEXT PRIMARY KEY,
            recipient_address TEXT NOT NULL,
            amount REAL NOT NULL,
            l1_block_height INTEGER NOT NULL,
            l1_block_time INTEGER NOT NULL,
            processed_time INTEGER NOT NULL
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_vars (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)
        conn.commit()
    
    # Create a vault watcher instance
    watcher = VaultWatcher(
        vault_address="celestia1abc123def456",
        l1_node_url="",  # Empty URL will use mock implementation
        ledger=mock_ledger,
        poll_interval=1,
        db_path=temp_db_path
    )
    
    # Test deposit data
    test_deposit = {
        "l1_tx_hash": "test_tx_123",
        "recipient_address": "fontana1abc123def456",
        "amount": 10.0,
        "l1_block_height": 1010,
        "l1_block_time": int(time.time())
    }
    
    # Process the deposit directly
    result = watcher._process_deposit(test_deposit)
    
    # Verify the result
    assert result is True
    
    # Verify the mock bridge handler was called
    mock_bridge_handler.assert_called_once_with(test_deposit, mock_ledger)
    
    # Verify the deposit was recorded in the database
    with sqlite3.connect(temp_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM vault_deposits WHERE l1_tx_hash = ?", ("test_tx_123",))
        count = cursor.fetchone()[0]
        assert count == 1


@patch('fontana.bridge.celestia.account_client.CelestiaAccountClient')
def test_vault_watcher_initialization(mock_celestia_client, mock_ledger, temp_db_path):
    """Test that the vault watcher initializes correctly with the right dependencies."""
    # Create mock Celestia client
    mock_client_instance = MagicMock()
    mock_celestia_client.return_value = mock_client_instance
    
    # Create a vault watcher
    watcher = VaultWatcher(
        vault_address="0xabcdef1234567890",
        l1_node_url="http://celestia-node:26657",
        ledger=mock_ledger,
        poll_interval=10,
        db_path=temp_db_path
    )
    
    # Verify the watcher was initialized correctly
    assert watcher.vault_address == "0xabcdef1234567890"
    assert watcher.l1_node_url == "http://celestia-node:26657"
    assert watcher.poll_interval == 10
    assert watcher.is_running is False
    assert watcher.monitor_thread is None
    assert watcher.ledger is mock_ledger


@patch('scripts.vault_watcher.handle_deposit_received')
@patch('threading.Thread')
@patch('fontana.bridge.celestia.account_client.CelestiaAccountClient')
def test_simulated_vault_watcher_run(mock_client_class, mock_thread, mock_bridge_handler, mock_ledger, temp_db_path):
    """
    Test a simulated run of the vault watcher daemon.

    This test simulates the vault watcher checking for new deposits
    and processing them through the bridge interface to the ledger.
    """
    # Set up mock thread
    mock_thread_instance = MagicMock()
    mock_thread.return_value = mock_thread_instance
    
    # Set up mock bridge handler
    mock_bridge_handler.return_value = True
    
    # Set up mock client
    mock_client = MagicMock()
    mock_client.get_current_height.return_value = 1030
    mock_client.get_deposits_since_height.return_value = [
        {
            "l1_tx_hash": "test_tx_1",
            "recipient_address": "fontana1abc",
            "amount": 10.0,
            "l1_block_height": 1010,
            "l1_block_time": int(time.time())
        },
        {
            "l1_tx_hash": "test_tx_2",
            "recipient_address": "fontana1def",
            "amount": 20.0,
            "l1_block_height": 1020,
            "l1_block_time": int(time.time())
        }
    ]
    mock_client_class.return_value = mock_client
    
    # Set up the database
    with sqlite3.connect(temp_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS vault_deposits (
            l1_tx_hash TEXT PRIMARY KEY,
            recipient_address TEXT NOT NULL,
            amount REAL NOT NULL,
            l1_block_height INTEGER NOT NULL,
            l1_block_time INTEGER NOT NULL,
            processed_time INTEGER NOT NULL
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_vars (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)
        cursor.execute(
            "INSERT INTO system_vars (key, value) VALUES ('last_l1_height_processed', '1000')"
        )
        conn.commit()
    
    # Create a vault watcher instance
    watcher = VaultWatcher(
        vault_address="celestia1abc123def456",
        l1_node_url="http://celestia-node:1317",  # Provide a URL to use the client
        ledger=mock_ledger,
        poll_interval=1,
        db_path=temp_db_path
    )
    
    # Replace the actual client with our mock
    watcher.l1_client = mock_client
    
    # Process the deposits directly without running the infinite loop
    last_height = watcher._get_last_processed_height()
    current_height = watcher._get_current_l1_height()
    deposits = watcher._get_deposits_in_range(last_height + 1, current_height)
    
    # Verify we got the expected deposits
    assert len(deposits) == 2
    
    # Process each deposit
    for deposit in deposits:
        watcher._process_deposit(deposit)
    
    # Verify that the bridge handler was called for each deposit
    assert mock_bridge_handler.call_count == 2
    
    # Verify the deposits were recorded in the database
    with sqlite3.connect(temp_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM vault_deposits")
        count = cursor.fetchone()[0]
        assert count == 2


def test_bridge_handler_ledger_integration(mock_ledger, mock_notification_manager):
    """
    Test the direct integration between the bridge handler and the ledger.

    This test focuses specifically on the bridge handler's interaction with the ledger,
    simulating the processing of a deposit event.
    """
    # Create a test deposit
    test_deposit = {
        "l1_tx_hash": "test_tx_123",
        "recipient_address": "fontana1abc123def456",
        "amount": 10.0,
        "l1_block_height": 1010,
        "l1_block_time": int(time.time())
    }

    # Set up the mock ledger to perform a realistic action
    def simulate_deposit_processing(deposit):
        # In a real scenario, this would create a UTXO
        # We simulate that behavior here
        return True

    mock_ledger.process_deposit_event.side_effect = simulate_deposit_processing

    # Call the bridge handler directly
    result = handle_deposit_received(test_deposit, mock_ledger)

    # Verify the result
    assert result is True
    
    # Verify the ledger was called with the right parameters
    mock_ledger.process_deposit_event.assert_called_once_with(test_deposit)
    
    # Verify notification was sent with the correct format
    mock_notification_manager.notify.assert_called_once_with(
        event_type=NotificationType.DEPOSIT_PROCESSED,
        data={
            "tx_hash": "test_tx_123",
            "recipient": "fontana1abc123def456",
            "amount": 10.0
        }
    )
