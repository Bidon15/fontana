"""
Tests for the vault watcher daemon.
"""
import pytest
import time
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch, ANY

from fontana.core.ledger.ledger import Ledger
from scripts.vault_watcher import VaultWatcher


@pytest.fixture
def mock_ledger():
    """Create a mock ledger."""
    ledger = MagicMock(spec=Ledger)
    return ledger


@pytest.fixture
def temp_db_path():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix='.db') as f:
        yield f.name


@patch('fontana.bridge.celestia.account_client.CelestiaAccountClient')
def test_initialization(mock_client_class, mock_ledger, temp_db_path):
    """Test initialization of the VaultWatcher."""
    # Set up mock
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    # Initialize VaultWatcher
    watcher = VaultWatcher(
        vault_address="celestia1abc123def456",
        l1_node_url="http://celestia-node:1317",
        ledger=mock_ledger,
        poll_interval=10,
        db_path=temp_db_path
    )
    
    # Verify initialization
    assert watcher.vault_address == "celestia1abc123def456"
    assert watcher.l1_node_url == "http://celestia-node:1317"
    assert watcher.poll_interval == 10
    assert watcher.ledger is mock_ledger
    assert watcher.db_path == temp_db_path
    assert watcher.is_running is False
    assert watcher.monitor_thread is None


@patch('sqlite3.connect')
def test_init_db(mock_connect, mock_ledger):
    """Test database initialization."""
    # Set up mock connection and cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value.__enter__.return_value = mock_conn
    
    # Initialize VaultWatcher
    VaultWatcher(
        vault_address="celestia1abc123def456",
        l1_node_url="",
        ledger=mock_ledger,
        poll_interval=1,
        db_path=":memory:"
    )
    
    # Verify SQL execution
    mock_cursor.execute.assert_any_call("""
                CREATE TABLE IF NOT EXISTS vault_deposits (
                    l1_tx_hash TEXT PRIMARY KEY,
                    recipient_address TEXT NOT NULL,
                    amount REAL NOT NULL,
                    l1_block_height INTEGER NOT NULL,
                    l1_block_time INTEGER NOT NULL,
                    processed_time INTEGER NOT NULL
                )
                """)
    
    mock_cursor.execute.assert_any_call("""
                CREATE TABLE IF NOT EXISTS system_vars (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """)


def test_get_last_processed_height(mock_ledger, temp_db_path):
    """Test getting the last processed height."""
    # Set up the database with a test value
    with sqlite3.connect(temp_db_path) as conn:
        cursor = conn.cursor()
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
    
    # Initialize the watcher
    watcher = VaultWatcher(
        vault_address="celestia1abc123def456",
        l1_node_url="",
        ledger=mock_ledger,
        poll_interval=1,
        db_path=temp_db_path
    )
    
    # Get the last processed height
    result = watcher._get_last_processed_height()
    
    # Verify the result
    assert result == 1000


def test_get_last_processed_height_not_found(mock_ledger, temp_db_path):
    """Test getting the last processed height when not found."""
    # Set up the database without a last processed height
    with sqlite3.connect(temp_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_vars (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)
        conn.commit()
    
    # Initialize the watcher
    watcher = VaultWatcher(
        vault_address="celestia1abc123def456",
        l1_node_url="",
        ledger=mock_ledger,
        poll_interval=1,
        db_path=temp_db_path
    )
    
    # Get the last processed height
    result = watcher._get_last_processed_height()
    
    # Verify the result
    assert result == 0
    
    # Verify the value was inserted
    with sqlite3.connect(temp_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_vars WHERE key = 'last_l1_height_processed'")
        value = cursor.fetchone()[0]
        assert int(value) == 0


def test_update_last_processed_height(mock_ledger, temp_db_path):
    """Test updating the last processed height."""
    # Set up the database
    with sqlite3.connect(temp_db_path) as conn:
        cursor = conn.cursor()
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
    
    # Initialize the watcher
    watcher = VaultWatcher(
        vault_address="celestia1abc123def456",
        l1_node_url="",
        ledger=mock_ledger,
        poll_interval=1,
        db_path=temp_db_path
    )
    
    # Update the last processed height
    watcher._update_last_processed_height(1050)
    
    # Verify the value was updated
    with sqlite3.connect(temp_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_vars WHERE key = 'last_l1_height_processed'")
        value = cursor.fetchone()[0]
        assert int(value) == 1050


def test_is_deposit_processed_true(mock_ledger, temp_db_path):
    """Test checking if a deposit is processed (true case)."""
    # Set up the database with a processed deposit
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
        cursor.execute(
            """
            INSERT INTO vault_deposits 
            (l1_tx_hash, recipient_address, amount, l1_block_height, l1_block_time, processed_time) 
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("test_tx_123", "fontana1abc123def456", 10.0, 1000, int(time.time()), int(time.time()))
        )
        conn.commit()
    
    # Initialize the watcher
    watcher = VaultWatcher(
        vault_address="celestia1abc123def456",
        l1_node_url="",
        ledger=mock_ledger,
        poll_interval=1,
        db_path=temp_db_path
    )
    
    # Check if the deposit is processed
    result = watcher._is_deposit_processed("test_tx_123")
    
    # Verify the result
    assert result is True


def test_is_deposit_processed_false(mock_ledger, temp_db_path):
    """Test checking if a deposit is processed (false case)."""
    # Set up the database without the deposit
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
        conn.commit()
    
    # Initialize the watcher
    watcher = VaultWatcher(
        vault_address="celestia1abc123def456",
        l1_node_url="",
        ledger=mock_ledger,
        poll_interval=1,
        db_path=temp_db_path
    )
    
    # Check if the deposit is processed
    result = watcher._is_deposit_processed("test_tx_123")
    
    # Verify the result
    assert result is False


def test_record_deposit(mock_ledger, temp_db_path):
    """Test recording a deposit."""
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
        conn.commit()
    
    # Test data
    deposit = {
        "l1_tx_hash": "test_tx_123",
        "recipient_address": "fontana1abc123def456",
        "amount": 10.0,
        "l1_block_height": 1000,
        "l1_block_time": 1714489547
    }
    
    # Initialize the watcher
    watcher = VaultWatcher(
        vault_address="celestia1abc123def456",
        l1_node_url="",
        ledger=mock_ledger,
        poll_interval=1,
        db_path=temp_db_path
    )
    
    # Record the deposit
    result = watcher._record_deposit(deposit)
    
    # Verify the result
    assert result is True
    
    # Verify the deposit was recorded
    with sqlite3.connect(temp_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vault_deposits WHERE l1_tx_hash = ?", ("test_tx_123",))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "test_tx_123"
        assert row[1] == "fontana1abc123def456"
        assert row[2] == 10.0
        assert row[3] == 1000
        assert row[4] == 1714489547


@patch('fontana.bridge.handler.notification_manager')
@patch('scripts.vault_watcher.handle_deposit_received')
def test_process_deposit_new(mock_bridge_handler, mock_notification_manager, mock_ledger, temp_db_path):
    """Test processing a new deposit."""
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
        conn.commit()
    
    # Set up mock bridge handler and mock ledger
    mock_bridge_handler.return_value = True
    mock_ledger.process_deposit_event.return_value = True  # Ensure the ledger mock returns True
    
    # Test data
    deposit = {
        "l1_tx_hash": "test_tx_123",
        "recipient_address": "fontana1abc123def456",
        "amount": 10.0,
        "l1_block_height": 1000,
        "l1_block_time": 1714489547
    }
    
    # Initialize the watcher
    watcher = VaultWatcher(
        vault_address="celestia1abc123def456",
        l1_node_url="",
        ledger=mock_ledger,
        poll_interval=1,
        db_path=temp_db_path
    )
    
    # Process the deposit
    result = watcher._process_deposit(deposit)
    
    # Verify the result
    assert result is True
    
    # Verify bridge handler was called
    mock_bridge_handler.assert_called_once_with(deposit, mock_ledger)
    
    # Verify the deposit was recorded
    with sqlite3.connect(temp_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM vault_deposits WHERE l1_tx_hash = ?", ("test_tx_123",))
        count = cursor.fetchone()[0]
        assert count == 1


@patch('threading.Thread')
def test_start_stop(mock_thread, mock_ledger, temp_db_path):
    """Test starting and stopping the watcher."""
    # Set up mock thread
    mock_thread_instance = MagicMock()
    mock_thread.return_value = mock_thread_instance
    
    # Initialize the watcher
    watcher = VaultWatcher(
        vault_address="celestia1abc123def456",
        l1_node_url="",
        ledger=mock_ledger,
        poll_interval=1,
        db_path=temp_db_path
    )
    
    # Start the watcher
    watcher.start()
    
    # Verify the thread was started
    assert watcher.is_running is True
    assert watcher.monitor_thread is mock_thread_instance
    mock_thread_instance.start.assert_called_once()
    
    # Stop the watcher
    watcher.stop()
    
    # Verify the thread was stopped
    assert watcher.is_running is False
    mock_thread_instance.join.assert_called_once()


@patch('fontana.bridge.celestia.account_client.CelestiaAccountClient')
def test_get_deposits_in_range(mock_client_class, mock_ledger, temp_db_path):
    """Test getting deposits in a range."""
    # Set up mock client
    mock_client = MagicMock()
    
    # Mock the deposit data
    mock_deposits = [
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
    
    # Setup the get_deposits_since_height method directly
    mock_client.get_deposits_since_height.return_value = mock_deposits
    mock_client_class.return_value = mock_client
    
    # Initialize the watcher
    watcher = VaultWatcher(
        vault_address="celestia1vault123",
        l1_node_url="http://celestia-node:1317",
        ledger=mock_ledger,
        poll_interval=1,
        db_path=temp_db_path
    )
    
    # Replace the client with our mock directly
    watcher.l1_client = mock_client
    
    # Get deposits in range
    deposits = watcher._get_deposits_in_range(1000, 1030)
    
    # Verify the result
    assert len(deposits) == 2
    
    # Verify get_deposits_since_height was called with correct parameters
    mock_client.get_deposits_since_height.assert_called_once_with(
        "celestia1vault123", 1000, 1030
    )
    
    # Check first deposit
    assert deposits[0]["l1_tx_hash"] == "test_tx_1"
    assert deposits[0]["recipient_address"] == "fontana1abc"
    
    # Check second deposit
    assert deposits[1]["l1_tx_hash"] == "test_tx_2"
    assert deposits[1]["recipient_address"] == "fontana1def"
