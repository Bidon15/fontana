"""
Tests for the Celestia account client.
"""
import pytest
from unittest.mock import MagicMock, patch, ANY

from fontana.bridge.celestia.account_client import CelestiaAccountClient, CelestiaTransaction


class TestCelestiaAccountClient:
    """Tests for the CelestiaAccountClient class."""
    
    @patch('fontana.bridge.celestia.account_client.LedgerClient')
    @patch('fontana.bridge.celestia.account_client.NetworkConfig')
    def test_initialization(self, mock_network_config, mock_ledger_client_class):
        """Test that the client initializes correctly."""
        # Set up the mock
        mock_client = MagicMock()
        mock_ledger_client_class.return_value = mock_client
        
        # Initialize the client with a patch to prevent actual client creation
        with patch.object(CelestiaAccountClient, '_initialize_client'):
            client = CelestiaAccountClient("http://celestia-node:1317")
            
            # Now manually set the client to our mock
            client.client = mock_client
            
            # Verify the client was initialized correctly
            assert client.node_url == "rest+http://celestia-node:1317"
            assert client.chain_id == "celestia"
            assert client.client is mock_client
    
    @patch('fontana.bridge.celestia.account_client.LedgerClient')
    def test_get_account_balance(self, mock_ledger_client_class):
        """Test getting account balance."""
        # Set up the mock
        mock_client = MagicMock()
        mock_client.query_bank_balance.return_value = 1000000  # 1 TIA in utia
        mock_ledger_client_class.return_value = mock_client
        
        # Initialize the client with a patch to prevent actual client creation
        with patch.object(CelestiaAccountClient, '_initialize_client'):
            client = CelestiaAccountClient("http://celestia-node:1317")
            
            # Manually set the mocked client
            client.client = mock_client
            
            # Get the balance
            balance = client.get_account_balance("celestia1abc123def456")
            
            # Verify the balance was retrieved correctly
            assert balance == 1000000
            mock_client.query_bank_balance.assert_called_once_with("celestia1abc123def456", "utia")
    
    def test_extract_recipient_from_memo(self):
        """Test extracting recipient from memo."""
        # Initialize the client directly
        client = CelestiaAccountClient("http://celestia-node:1317")
        
        # Test valid memo
        valid_memo = "deposit:fontana1abc123def456"
        recipient = client._extract_recipient_from_memo(valid_memo)
        assert recipient == "fontana1abc123def456"
        
        # Test invalid memos
        assert client._extract_recipient_from_memo("") is None
        assert client._extract_recipient_from_memo("invalid") is None
        assert client._extract_recipient_from_memo("deposit:") is None
    
    @patch('fontana.bridge.celestia.account_client.LedgerClient')
    def test_get_deposits_since_height(self, mock_ledger_client_class):
        """Test getting deposits since a specific height."""
        # Set up the mock client response
        mock_client = MagicMock()
        
        # Mock the query response for transactions
        mock_tx_response = {
            "tx_responses": [
                {
                    "txhash": "tx_hash_1",
                    "height": "1001",
                    "tx": {
                        "body": {
                            "messages": [
                                {
                                    "@type": "/cosmos.bank.v1beta1.MsgSend",
                                    "from_address": "celestia1sender1",
                                    "to_address": "celestia1vault123",
                                    "amount": [{"denom": "utia", "amount": "1000000"}]
                                }
                            ],
                            "memo": "deposit:fontana1recipient1"
                        }
                    }
                },
                {
                    "txhash": "tx_hash_2",
                    "height": "1002",
                    "tx": {
                        "body": {
                            "messages": [
                                {
                                    "@type": "/cosmos.bank.v1beta1.MsgSend",
                                    "from_address": "celestia1sender2",
                                    "to_address": "celestia1vault123",
                                    "amount": [{"denom": "utia", "amount": "2000000"}]
                                }
                            ],
                            "memo": "deposit:fontana1recipient2"
                        }
                    }
                }
            ]
        }
        
        # Set up mock client methods
        mock_client.query.return_value = mock_tx_response
        mock_client.query_status.return_value = {"sync_info": {"latest_block_height": "1005"}}
        mock_ledger_client_class.return_value = mock_client
        
        # Initialize the client with a patch to prevent actual client creation
        with patch.object(CelestiaAccountClient, '_initialize_client'):
            client = CelestiaAccountClient("http://celestia-node:1317")
            
            # Manually set the mocked client
            client.client = mock_client
            
            # Get deposits
            deposits = client.get_deposits_since_height("celestia1vault123", 1000, 1003)
            
            # Verify the deposits were retrieved correctly
            assert len(deposits) == 2
            
            # Check first deposit
            assert deposits[0]["l1_tx_hash"] == "tx_hash_1"
            assert deposits[0]["recipient_address"] == "fontana1recipient1"
            assert deposits[0]["amount"] == 1.0
            assert deposits[0]["l1_block_height"] == 1001
            
            # Check second deposit
            assert deposits[1]["l1_tx_hash"] == "tx_hash_2"
            assert deposits[1]["recipient_address"] == "fontana1recipient2"
            assert deposits[1]["amount"] == 2.0
            assert deposits[1]["l1_block_height"] == 1002
            
            # Verify query was called correctly
            mock_client.query.assert_called_once_with(
                "/cosmos/tx/v1beta1/txs?events=transfer.recipient='celestia1vault123',transfer.sender='celestia1vault123'&pagination.limit=100&events=tx.height>=1000"
            )
