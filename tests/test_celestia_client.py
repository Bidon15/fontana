"""
Tests for the Celestia DA client.
"""
import pytest
from unittest.mock import MagicMock, patch
import json

from fontana.core.da.client import CelestiaClient, CelestiaSubmissionError
from fontana.core.models.block import Block, BlockHeader
from fontana.core.notifications import NotificationManager, NotificationType


@pytest.fixture
def mock_notification_manager():
    """Create a mock notification manager."""
    manager = MagicMock(spec=NotificationManager)
    return manager


@pytest.fixture
def mock_block():
    """Create a mock block for testing."""
    header = BlockHeader(
        height=123,
        prev_hash="prev-hash-123",
        state_root="state-root-123",
        timestamp=1714489547,
        tx_count=2,
        fee_schedule_id="test-fee-schedule",
        hash="block-hash-123",
        blob_ref=""  # Add empty blob_ref to satisfy validation
    )
    
    return Block(
        header=header,
        transactions=[]
    )


@pytest.fixture
def celestia_client(mock_notification_manager):
    """Create a CelestiaClient instance for testing."""
    with patch('pylestia.node_api.Client') as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock the blob API
        mock_client.blob = MagicMock()
        
        client = CelestiaClient(mock_notification_manager)
        
        # Set enabled to True for testing
        client.enabled = True
        
        return client


class TestCelestiaClient:
    """Tests for the CelestiaClient class."""
    
    def test_namespace_for_block(self, celestia_client):
        """Test generating a namespace ID for a block."""
        # Get namespace for block height 123
        namespace_id = celestia_client._get_namespace_for_block(123)
        
        # Verify it's a hex string of the right length (8 bytes = 16 hex chars)
        assert isinstance(namespace_id, str)
        assert len(namespace_id) == 16
        
        # Test that the same height always produces the same namespace
        namespace_id2 = celestia_client._get_namespace_for_block(123)
        assert namespace_id == namespace_id2
        
        # Test that different heights produce different namespaces
        namespace_id3 = celestia_client._get_namespace_for_block(124)
        assert namespace_id != namespace_id3
    
    def test_namespace_id_bytes(self, celestia_client):
        """Test converting a hex namespace ID to bytes."""
        hex_namespace = "0123456789abcdef"
        namespace_bytes = celestia_client._namespace_id_bytes(hex_namespace)
        
        assert isinstance(namespace_bytes, bytes)
        assert len(namespace_bytes) == 8
        assert namespace_bytes.hex() == hex_namespace
    
    def test_post_block_success(self, celestia_client, mock_block):
        """Test successful block submission to Celestia."""
        # Set up mock response for blob.submit
        mock_response = MagicMock()
        mock_response.height = 1000  # Celestia height
        celestia_client.client.blob.submit = MagicMock(return_value=mock_response)
        
        # Mock the Namespace and Blob classes
        with patch('pylestia.types.Namespace') as mock_namespace:
            with patch('pylestia.types.Blob') as mock_blob:
                # Post the block
                blob_ref = celestia_client.post_block(mock_block)
                
                # Verify Namespace and Blob were created correctly
                namespace_id = celestia_client._get_namespace_for_block(mock_block.header.height)
                namespace_bytes = celestia_client._namespace_id_bytes(namespace_id)
                mock_namespace.assert_called_once_with(namespace_bytes)
                
                # Verify block data was encoded properly
                block_json = mock_block.model_dump_json().encode()
                mock_blob.assert_called_once_with(block_json)
                
                # Verify blob.submit was called with correct arguments
                submit_call = celestia_client.client.blob.submit.call_args
                assert submit_call is not None
                
                # Extract args
                kwargs = submit_call[1]
                
                # Check namespace_id parameter
                assert kwargs['namespace_id'] == mock_namespace.return_value
                
                # Check data parameter
                assert kwargs['data'] == mock_blob.return_value
                
                # Check blob_ref format
                expected_blob_ref = f"1000:{namespace_id}"
                assert blob_ref == expected_blob_ref
                
                # Check that block was added to pending submissions
                assert namespace_id in celestia_client.pending_submissions
                assert celestia_client.pending_submissions[namespace_id]["block_height"] == mock_block.header.height
                assert celestia_client.pending_submissions[namespace_id]["celestia_height"] == 1000
                assert celestia_client.pending_submissions[namespace_id]["blob_ref"] == expected_blob_ref
    
    def test_post_block_error(self, celestia_client, mock_block):
        """Test handling of errors during block submission."""
        # Set up mock to raise Exception
        celestia_client.client.blob.submit = MagicMock(side_effect=Exception("Test error"))
        
        # Test that the error is caught and wrapped in CelestiaSubmissionError
        with pytest.raises(CelestiaSubmissionError) as exc_info:
            celestia_client.post_block(mock_block)
        
        # Verify the error message contains the original error
        assert "Failed to submit block: Test error" in str(exc_info.value)
    
    def test_post_block_disabled(self, mock_block):
        """Test submitting a block when Celestia is disabled."""
        # Create a client with disabled Celestia
        with patch('pylestia.node_api.Client') as mock_client_class:
            client = CelestiaClient()
            
            # Ensure it's disabled
            assert not client.enabled
            
            # Post a block - should return a mock blob ref in test mode
            blob_ref = client.post_block(mock_block)
            
            assert blob_ref == f"mock-blob-ref-{mock_block.header.height}"
    
    def test_fetch_block_data_success(self, celestia_client, mock_block):
        """Test successful block data fetching from Celestia."""
        # First post the block to get a blob ref
        mock_submit_response = MagicMock()
        mock_submit_response.height = 1000
        celestia_client.client.blob.submit = MagicMock(return_value=mock_submit_response)
        
        with patch('pylestia.types.Namespace'):
            with patch('pylestia.types.Blob'):
                blob_ref = celestia_client.post_block(mock_block)
        
        # Now set up mock for get call
        block_json = mock_block.model_dump_json()
        mock_get_response = MagicMock()
        mock_get_response.data = [block_json.encode()]
        celestia_client.client.blob.get = MagicMock(return_value=mock_get_response)
        
        # Mock the Namespace class
        with patch('pylestia.types.Namespace') as mock_namespace:
            # Fetch the block data
            block_data = celestia_client.fetch_block_data(blob_ref)
            
            # Verify Namespace was created correctly
            namespace_id = blob_ref.split(":")[1]
            namespace_bytes = celestia_client._namespace_id_bytes(namespace_id)
            mock_namespace.assert_called_once_with(namespace_bytes)
            
            # Verify get was called with correct arguments
            get_call = celestia_client.client.blob.get.call_args
            assert get_call is not None
            
            # Extract args
            kwargs = get_call[1]
            
            # Check parameters
            assert kwargs['height'] == 1000
            assert kwargs['namespace_id'] == mock_namespace.return_value
            
            # Check returned data
            assert block_data["header"]["height"] == mock_block.header.height
            assert block_data["header"]["hash"] == mock_block.header.hash
    
    def test_check_confirmation_success(self, celestia_client, mock_block, mock_notification_manager):
        """Test successful confirmation check."""
        # First post the block
        mock_submit_response = MagicMock()
        mock_submit_response.height = 1000
        celestia_client.client.blob.submit = MagicMock(return_value=mock_submit_response)
        
        with patch('pylestia.types.Namespace'):
            with patch('pylestia.types.Blob'):
                blob_ref = celestia_client.post_block(mock_block)
        
        namespace_id = blob_ref.split(":")[1]
        
        # Now set up mock for get call to indicate the block exists
        mock_get_response = MagicMock()
        mock_get_response.data = [b'some-data']
        celestia_client.client.blob.get = MagicMock(return_value=mock_get_response)
        
        # Mock the Namespace class
        with patch('pylestia.types.Namespace') as mock_namespace:
            # Check confirmation
            result = celestia_client.check_confirmation(namespace_id)
            
            # Verify Namespace was created correctly
            namespace_bytes = celestia_client._namespace_id_bytes(namespace_id)
            mock_namespace.assert_called_once_with(namespace_bytes)
            
            # Verify result
            assert result is True
            
            # Verify submission is marked as confirmed
            assert celestia_client.pending_submissions[namespace_id]["confirmed"] is True
            
            # Verify notification was sent
            mock_notification_manager.notify.assert_called_once_with(
                notification_type=NotificationType.BLOCK_COMMITTED_TO_DA,
                block_height=mock_block.header.height
            )
    
    def test_check_confirmation_not_found(self, celestia_client, mock_block):
        """Test confirmation check when block is not found."""
        # First post the block
        mock_submit_response = MagicMock()
        mock_submit_response.height = 1000
        celestia_client.client.blob.submit = MagicMock(return_value=mock_submit_response)
        
        with patch('pylestia.types.Namespace'):
            with patch('pylestia.types.Blob'):
                blob_ref = celestia_client.post_block(mock_block)
        
        namespace_id = blob_ref.split(":")[1]
        
        # Now set up mock for get call to indicate the block does not exist
        mock_get_response = MagicMock()
        mock_get_response.data = []  # Empty data means not found
        celestia_client.client.blob.get = MagicMock(return_value=mock_get_response)
        
        # Mock the Namespace class
        with patch('pylestia.types.Namespace') as mock_namespace:
            # Check confirmation
            result = celestia_client.check_confirmation(namespace_id)
            
            # Verify result
            assert result is False
            
            # Verify submission is not marked as confirmed
            assert celestia_client.pending_submissions[namespace_id]["confirmed"] is False
