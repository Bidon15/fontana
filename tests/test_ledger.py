"""
Tests for the Ledger implementation.
"""
import pytest
import json
import hashlib
from unittest.mock import Mock, patch, MagicMock

from fontana.core.models.utxo import UTXO, UTXORef
from fontana.core.models.transaction import SignedTransaction
from fontana.core.ledger import Ledger, TransactionValidationError, InvalidSignatureError, \
    InputNotFoundError, InputSpentError, InsufficientFundsError
from fontana.wallet import Wallet


def create_mock_utxo(txid: str, output_index: int, recipient: str, amount: float, status: str = "unspent"):
    """Create a mock UTXO."""
    return UTXO(
        txid=txid,
        output_index=output_index,
        recipient=recipient,
        amount=amount,
        status=status
    )


def create_mock_tx(inputs, outputs, sender, fee=0.01, sign=True):
    """Create a mock transaction."""
    # Calculate txid as hash of inputs and outputs
    tx_data = {
        "inputs": [input_ref.model_dump() for input_ref in inputs],
        "outputs": [output.to_sql_row() for output in outputs],
        "fee": fee
    }
    txid = hashlib.sha256(json.dumps(tx_data, sort_keys=True).encode()).hexdigest()
    
    tx = SignedTransaction(
        txid=txid,
        sender_address=sender.get_address(),
        inputs=inputs,
        outputs=outputs,
        fee=fee,
        payload_hash="test-payload-hash",
        timestamp=1714489547,
        signature="placeholder"
    )
    
    # Sign the transaction if requested
    if sign:
        # Create the message to sign
        tx_data = {
            "txid": tx.txid,
            "sender_address": tx.sender_address,
            "inputs": [input_ref.model_dump() for input_ref in tx.inputs],
            "outputs": [output.to_sql_row() for output in tx.outputs],
            "fee": tx.fee,
            "payload_hash": tx.payload_hash,
            "timestamp": tx.timestamp
        }
        message = json.dumps(tx_data, sort_keys=True).encode()
        
        # Sign with the sender's key
        tx.signature = sender.sign(message=message)
    
    return tx


@pytest.fixture
def mock_db():
    """Create a mock DB with patched functions."""
    with patch("fontana.core.ledger.ledger.db") as mock_db:
        # Setup default mock behaviors
        mock_db.get_connection.return_value = MagicMock()
        
        # Mock cursor for UTXO queries
        mock_cursor = MagicMock()
        mock_db.get_connection.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []  # Empty by default
        
        yield mock_db


@pytest.fixture
def mock_tree():
    """Create a mock Merkle tree."""
    with patch("fontana.core.ledger.ledger.SparseMerkleTree") as mock_tree_class:
        mock_tree = MagicMock()
        mock_tree_class.return_value = mock_tree
        
        # Setup default mock behaviors
        mock_tree.get_root.return_value = "mock-state-root"
        
        yield mock_tree


@pytest.fixture
def test_wallets():
    """Create test wallets for sender and recipient."""
    sender = Wallet.generate()
    recipient = Wallet.generate()
    return {"sender": sender, "recipient": recipient}


def test_ledger_init(mock_db, mock_tree):
    """Test Ledger initialization."""
    ledger = Ledger()
    
    # Verify tree was initialized
    assert mock_tree.method_calls
    
    # Verify DB was queried for UTXOs
    mock_db.get_connection.assert_called()


@patch("fontana.core.ledger.ledger.Signer.verify")
def test_validate_signature(mock_verify, mock_db, mock_tree, test_wallets):
    """Test transaction signature validation."""
    # Setup
    ledger = Ledger()
    sender = test_wallets["sender"]
    recipient = test_wallets["recipient"]
    
    # Create a test transaction
    utxo_input = UTXORef(txid="test-txid", output_index=0)
    utxo_output = create_mock_utxo(
        txid="new-txid", 
        output_index=0, 
        recipient=recipient.get_address(),
        amount=1.0
    )
    tx = create_mock_tx([utxo_input], [utxo_output], sender)
    
    # Configure mock to return True for signature verification
    mock_verify.return_value = True
    
    # Test valid signature
    assert ledger._validate_signature(tx)
    mock_verify.assert_called_once()
    
    # Test invalid signature
    mock_verify.reset_mock()
    mock_verify.return_value = False
    assert not ledger._validate_signature(tx)
    mock_verify.assert_called_once()


def test_check_inputs_spendable(mock_db, mock_tree, test_wallets):
    """Test checking if inputs are spendable."""
    # Setup
    ledger = Ledger()
    sender = test_wallets["sender"]
    recipient = test_wallets["recipient"]
    
    # Create a test transaction
    utxo_ref = UTXORef(txid="test-txid", output_index=0)
    utxo_output = create_mock_utxo(
        txid="new-txid", 
        output_index=0, 
        recipient=recipient.get_address(),
        amount=1.0
    )
    tx = create_mock_tx([utxo_ref], [utxo_output], sender)
    
    # Configure mock cursor to return a valid UTXO
    mock_cursor = mock_db.get_connection.return_value.cursor.return_value
    mock_cursor.fetchone.return_value = {
        "txid": "test-txid",
        "output_index": 0,
        "recipient": sender.get_address(),
        "amount": 2.0,
        "status": "unspent"
    }
    mock_db.dict_from_row.return_value = {
        "txid": "test-txid",
        "output_index": 0,
        "recipient": sender.get_address(),
        "amount": 2.0,
        "status": "unspent"
    }
    
    # Test valid input
    input_utxos = ledger._check_inputs_spendable(tx)
    assert len(input_utxos) == 1
    assert input_utxos[0].txid == "test-txid"
    assert input_utxos[0].output_index == 0
    
    # Test input not found
    mock_cursor.fetchone.return_value = None
    with pytest.raises(InputNotFoundError):
        ledger._check_inputs_spendable(tx)
    
    # Test input already spent
    mock_cursor.fetchone.return_value = {
        "txid": "test-txid",
        "output_index": 0,
        "recipient": sender.get_address(),
        "amount": 2.0,
        "status": "spent"
    }
    mock_db.dict_from_row.return_value = {
        "txid": "test-txid",
        "output_index": 0,
        "recipient": sender.get_address(),
        "amount": 2.0,
        "status": "spent"
    }
    with pytest.raises(InputSpentError):
        ledger._check_inputs_spendable(tx)
    
    # Test input not belonging to sender
    mock_cursor.fetchone.return_value = {
        "txid": "test-txid",
        "output_index": 0,
        "recipient": "someone-else",
        "amount": 2.0,
        "status": "unspent"
    }
    mock_db.dict_from_row.return_value = {
        "txid": "test-txid",
        "output_index": 0,
        "recipient": "someone-else",
        "amount": 2.0,
        "status": "unspent"
    }
    with pytest.raises(TransactionValidationError):
        ledger._check_inputs_spendable(tx)


def test_check_sufficient_funds(mock_db, mock_tree, test_wallets):
    """Test checking for sufficient funds."""
    # Setup
    ledger = Ledger()
    sender = test_wallets["sender"]
    recipient = test_wallets["recipient"]
    
    # Create input UTXOs with different amounts
    input_utxo_sufficient = create_mock_utxo(
        txid="test-txid-1", 
        output_index=0, 
        recipient=sender.get_address(),
        amount=2.0
    )
    input_utxo_insufficient = create_mock_utxo(
        txid="test-txid-2", 
        output_index=0, 
        recipient=sender.get_address(),
        amount=0.5
    )
    
    # Create a test transaction
    utxo_ref = UTXORef(txid="test-txid", output_index=0)
    utxo_output = create_mock_utxo(
        txid="new-txid", 
        output_index=0, 
        recipient=recipient.get_address(),
        amount=1.0
    )
    tx = create_mock_tx([utxo_ref], [utxo_output], sender, fee=0.1)
    
    # Test sufficient funds
    assert ledger._check_sufficient_funds([input_utxo_sufficient], tx)
    
    # Test insufficient funds
    with pytest.raises(InsufficientFundsError):
        ledger._check_sufficient_funds([input_utxo_insufficient], tx)


@patch("fontana.core.ledger.ledger.Signer.verify")
def test_apply_transaction(mock_verify, mock_db, mock_tree, test_wallets):
    """Test applying a transaction to the ledger."""
    # Setup
    ledger = Ledger()
    sender = test_wallets["sender"]
    recipient = test_wallets["recipient"]
    
    # Create a test transaction
    utxo_ref = UTXORef(txid="test-txid", output_index=0)
    utxo_output = create_mock_utxo(
        txid="new-txid", 
        output_index=0, 
        recipient=recipient.get_address(),
        amount=1.0
    )
    tx = create_mock_tx([utxo_ref], [utxo_output], sender, fee=0.1)
    
    # Configure mocks
    mock_verify.return_value = True
    
    mock_cursor = mock_db.get_connection.return_value.cursor.return_value
    mock_cursor.fetchone.return_value = {
        "txid": "test-txid",
        "output_index": 0,
        "recipient": sender.get_address(),
        "amount": 2.0,
        "status": "unspent"
    }
    mock_db.dict_from_row.return_value = {
        "txid": "test-txid",
        "output_index": 0,
        "recipient": sender.get_address(),
        "amount": 2.0,
        "status": "unspent"
    }
    
    # Test successful application
    assert ledger.apply_transaction(tx)
    
    # Verify DB operations
    mock_db.mark_utxo_spent.assert_called_with("test-txid", 0)
    mock_db.insert_transaction.assert_called_with(tx)
    mock_db.insert_utxo.assert_called_with(utxo_output)
    
    # Verify state tree operations
    mock_tree.update.assert_called()
    
    # Test with invalid signature
    mock_verify.return_value = False
    with pytest.raises(InvalidSignatureError):
        ledger.apply_transaction(tx)


def test_get_current_state_root(mock_db, mock_tree):
    """Test getting the current state root."""
    # Setup
    ledger = Ledger()
    
    # Reset mock because it's called in __init__
    mock_tree.reset_mock()
    mock_tree.get_root.return_value = "test-state-root"
    
    # Test
    assert ledger.get_current_state_root() == "test-state-root"
    assert mock_tree.get_root.called  # Just check that it was called, don't check count


def test_get_balance(mock_db, mock_tree):
    """Test getting an address balance."""
    # Setup
    ledger = Ledger()
    address = "test-address"
    
    # Configure mock
    mock_db.fetch_unspent_utxos.return_value = [
        create_mock_utxo("txid1", 0, address, 1.0),
        create_mock_utxo("txid2", 0, address, 2.0),
        create_mock_utxo("txid3", 0, address, 3.0)
    ]
    
    # Test
    assert ledger.get_balance(address) == 6.0
    mock_db.fetch_unspent_utxos.assert_called_with(address)


def test_process_deposit_event(mock_db, mock_tree):
    """Test processing a deposit event."""
    # Setup
    ledger = Ledger()
    
    deposit_details = {
        "tx_hash": "test-l1-tx",
        "rollup_wallet_address": "test-recipient",
        "amount": 5.0,
        "height": 123,
        "timestamp": 1714489547
    }
    
    # Test
    assert ledger.process_deposit_event(deposit_details)
    
    # Verify DB operations
    mock_db.insert_vault_deposit.assert_called_once()
    mock_db.insert_utxo.assert_called_once()
    mock_db.mark_deposit_processed.assert_called_once_with(
        "test-l1-tx", "test-recipient"
    )
    
    # Verify state tree update
    mock_tree.update.assert_called_once()


def test_process_withdrawal_event(mock_db, mock_tree):
    """Test processing a withdrawal confirmation event."""
    # Setup
    ledger = Ledger()
    
    # Need to reset all connection mocks because they're called during ledger initialization
    connection_mock = mock_db.get_connection.return_value
    connection_mock.reset_mock()
    connection_mock.cursor.reset_mock()
    connection_mock.commit.reset_mock()
    connection_mock.close.reset_mock()
    
    withdrawal_details = {
        "withdrawal_tx_id": "test-withdrawal-tx",
        "l1_tx_hash": "test-l1-tx"
    }
    
    # Test
    assert ledger.process_withdrawal_event(withdrawal_details)
    
    # Verify DB operations
    connection_mock.cursor.assert_called_once()
    cursor_mock = connection_mock.cursor.return_value
    cursor_mock.execute.assert_called_with(
        "UPDATE vault_withdrawals SET l1_tx_hash = ?, l1_confirmed = 1 WHERE withdrawal_tx_id = ?", 
        ("test-l1-tx", "test-withdrawal-tx")
    )
    connection_mock.commit.assert_called_once()
    connection_mock.close.assert_called_once()
