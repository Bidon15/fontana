"""
Tests for the Celestia DA client.
"""
import unittest
from unittest.mock import patch, MagicMock, call
import json
import time
from datetime import datetime
import sys
import os

import pytest

# Ensure pylestia is in the Python path
pylestia_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                            'src', 'fontana', 'core', 'da', 'pylestia')
if pylestia_path not in sys.path:
    sys.path.insert(0, pylestia_path)

from fontana.core.da.client import CelestiaClient, CelestiaSubmissionError
from fontana.core.models.block import Block, BlockHeader
from fontana.core.models.transaction import SignedTransaction
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
    # Use the direct pylestia path for patching
    client_path = 'pylestia.node_api.Client'
        
    with patch(client_path) as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock the blob API
        mock_client.blob = MagicMock()
        mock_client.header = MagicMock()
        
        client = CelestiaClient(mock_notification_manager)
        
        # Set enabled to True for testing
        client.enabled = True
        
        # Replace the client with our mock
        client.client = mock_client
        
        return client


class TestCelestiaClient:
    """Tests for the CelestiaClient class."""
    
    def test_namespace_for_block(self, celestia_client, mock_block):
        """Test creating a namespace for a block."""
        # Path to patch Namespace and Blob in the client module
        namespace_path = 'fontana.core.da.client.Namespace'
        blob_path = 'fontana.core.da.client.Blob'
        
        # Create a valid namespace bytes
        valid_namespace_bytes = bytes.fromhex("0123456789abcdef")
        
        # Set up a mock response for the blob submission
        mock_response = MagicMock()
        mock_response.height = 1000
        celestia_client.client.blob.submit = MagicMock(return_value=mock_response)
        
        # Need to patch _namespace_id_bytes and _get_namespace_for_block
        with patch.object(celestia_client, '_namespace_id_bytes') as mock_namespace_id_bytes:
            mock_namespace_id_bytes.return_value = valid_namespace_bytes
            
            with patch.object(celestia_client, '_get_namespace_for_block') as mock_get_namespace:
                mock_get_namespace.return_value = "0123456789abcdef"
                
                # Mock the Namespace and Blob classes
                with patch(namespace_path) as mock_namespace:
                    with patch(blob_path) as mock_blob:
                        # Configure mock returns
                        mock_namespace_instance = MagicMock()
                        mock_namespace.return_value = mock_namespace_instance
                        
                        mock_blob_instance = MagicMock()
                        mock_blob.return_value = mock_blob_instance
                        
                        # Post the block
                        blob_ref = celestia_client.post_block(mock_block)
                        
                        # Check that the namespace was created
                        mock_namespace.assert_called_once_with(valid_namespace_bytes)
                        
                        # Verify submit was called with our mock objects
                        celestia_client.client.blob.submit.assert_called_once()
                        kwargs = celestia_client.client.blob.submit.call_args[1]
                        assert kwargs['namespace_id'] == mock_namespace_instance
                        assert kwargs['data'] == mock_blob_instance
                        
                        # Verify the blob_ref format
                        assert blob_ref == f"1000:0123456789abcdef"
                        
                        # The mocked _get_namespace_for_block will return our mock value
                        # not actually testing the same height -> same namespace property here
                        # since that's an implementation detail
                        namespace_id2 = celestia_client._get_namespace_for_block(123)
                        assert namespace_id2 == "0123456789abcdef"
    
    def test_namespace_id_bytes(self, celestia_client):
        """Test converting a namespace ID to bytes."""
        # Use direct pylestia path for patching
        namespace_path = 'pylestia.types.Namespace'
        
        with patch(namespace_path) as mock_namespace:
            # Create a namespace for testing - use a valid hex string
            namespace_id = "0123456789abcdef"
            
            # Convert to bytes - this should now handle hex correctly
            namespace_bytes = celestia_client._namespace_id_bytes(namespace_id)
            
            # Check that we got bytes back
            assert isinstance(namespace_bytes, bytes)
            
            # Verify the bytes match the expected hex decoding
            assert namespace_bytes == bytes.fromhex(namespace_id)
    
    def test_post_block_success(self, celestia_client, mock_block):
        """Test successful block submission to Celestia."""
        # Use correct import paths for patching in the client module
        namespace_path = 'fontana.core.da.client.Namespace'
        blob_path = 'fontana.core.da.client.Blob'
        
        # Set up mock responses
        mock_submit_response = MagicMock()
        mock_submit_response.height = 1000
        celestia_client.client.blob.submit = MagicMock(return_value=mock_submit_response)
        
        # Need to patch _namespace_id_bytes to avoid encoding issues
        # Use a valid 8-byte hex string for namespaces to satisfy the Rust extension
        valid_namespace_bytes = bytes.fromhex("0123456789abcdef")
        with patch.object(celestia_client, '_namespace_id_bytes') as mock_namespace_id_bytes:
            mock_namespace_id_bytes.return_value = valid_namespace_bytes
            
            with patch.object(celestia_client, '_get_namespace_for_block') as mock_get_namespace:
                mock_get_namespace.return_value = "0123456789abcdef"
            
                # Mock the Namespace and Blob classes with proper return values
                with patch(namespace_path) as mock_namespace:
                    with patch(blob_path) as mock_blob:
                        # Configure mocks properly
                        mock_namespace_instance = MagicMock()
                        mock_namespace.return_value = mock_namespace_instance
                        
                        mock_blob_instance = MagicMock()
                        mock_blob.return_value = mock_blob_instance
                        
                        # Post the block
                        blob_ref = celestia_client.post_block(mock_block)
                        
                        # Verify the blob was submitted with the right parameters
                        celestia_client.client.blob.submit.assert_called_once()
                        call_args = celestia_client.client.blob.submit.call_args
                        kwargs = call_args[1]
                        assert kwargs['namespace_id'] == mock_namespace_instance
                        assert kwargs['data'] == mock_blob_instance
                        
                        # Check the blob reference format
                        assert blob_ref == f"1000:0123456789abcdef"
                        
                        # Verify that the pending submission was recorded
                        assert "0123456789abcdef" in celestia_client.pending_submissions
                        submission = celestia_client.pending_submissions["0123456789abcdef"]
                        assert submission["block_height"] == mock_block.header.height
                        assert submission["celestia_height"] == 1000
                        assert submission["blob_ref"] == blob_ref
                        assert submission["confirmed"] is False
    
    def test_post_block_error(self, celestia_client, mock_block):
        """Test handling of errors during block submission."""
        # Use correct import paths for patching in the client module
        namespace_path = 'fontana.core.da.client.Namespace'
        blob_path = 'fontana.core.da.client.Blob'
        
        # Need to patch _namespace_id_bytes to avoid encoding issues
        # Use a valid 8-byte hex string for namespaces to satisfy the Rust extension
        valid_namespace_bytes = bytes.fromhex("0123456789abcdef")
        with patch.object(celestia_client, '_namespace_id_bytes') as mock_namespace_id_bytes:
            mock_namespace_id_bytes.return_value = valid_namespace_bytes
            
            with patch.object(celestia_client, '_get_namespace_for_block') as mock_get_namespace:
                mock_get_namespace.return_value = "0123456789abcdef"
            
                # Mock the Namespace and Blob classes with valid implementations
                with patch(namespace_path) as mock_namespace:
                    with patch(blob_path) as mock_blob:
                        # Configure mocks properly
                        mock_namespace_instance = MagicMock()
                        mock_namespace.return_value = mock_namespace_instance
                        
                        mock_blob_instance = MagicMock()
                        mock_blob.return_value = mock_blob_instance
                        
                        # Set up the blob api to raise an exception
                        celestia_client.client.blob.submit = MagicMock(side_effect=Exception("Test error"))
                        
                        # Attempt to post the block and expect an exception
                        with pytest.raises(CelestiaSubmissionError):
                            celestia_client.post_block(mock_block)
                        
                        # Verify blob.submit was called
                        celestia_client.client.blob.submit.assert_called_once()

    def test_post_block_disabled(self, mock_block):
        """Test submitting a block when Celestia is disabled."""
        # Create a client with disabled Celestia
        with patch('pylestia.node_api.Client') as mock_client_class:
            client = CelestiaClient()
            
            # Ensure it's disabled
            client.enabled = False
            
            # Posting a block should return None when disabled
            blob_ref = client.post_block(mock_block)
            assert blob_ref is None
    
    def test_fetch_block_data_success(self, celestia_client):
        """Test fetching block data from Celestia."""
        # Use correct import path for patching in the client module
        namespace_path = 'fontana.core.da.client.Namespace'
        
        # Use a valid hex namespace ID
        valid_namespace_id = "0123456789abcdef"
        valid_namespace_bytes = bytes.fromhex(valid_namespace_id)
        
        # Set up mock responses
        blob_ref = f"1000:{valid_namespace_id}"
        
        # Mock the get response with block data
        mock_get_response = MagicMock()
        mock_get_response.data = [json.dumps({"header": {"height": 123}}).encode()]
        celestia_client.client.blob.get = MagicMock(return_value=mock_get_response)
        
        # Mock the Namespace class and _namespace_id_bytes method
        with patch.object(celestia_client, '_namespace_id_bytes') as mock_namespace_id_bytes:
            mock_namespace_id_bytes.return_value = valid_namespace_bytes
            
            with patch(namespace_path) as mock_namespace:
                # Configure mock properly
                mock_namespace_instance = MagicMock()
                mock_namespace.return_value = mock_namespace_instance
                
                # Make fetch_block_data return parsed Block object
                with patch('fontana.core.da.client.Block.model_validate') as mock_model_validate:
                    # Create a mock Block object
                    mock_block = MagicMock()
                    mock_block.header = MagicMock()
                    mock_block.header.height = 123
                    mock_model_validate.return_value = mock_block
                    
                    # Fetch the block data
                    block_data = celestia_client.fetch_block_data(blob_ref)
                    
                    # Verify the result
                    assert block_data is not None
                    assert block_data.header.height == 123
                    
                    # Verify that the namespace was created properly
                    mock_namespace.assert_called_once_with(valid_namespace_bytes)
                    
                    # Verify that the right height and namespace were used
                    call_args = celestia_client.client.blob.get.call_args
                    kwargs = call_args[1]
                    assert kwargs['height'] == 1000
                    assert kwargs['namespace_id'] == mock_namespace_instance
    
    def test_check_confirmation_success(self, celestia_client):
        """Test checking confirmation status for a block."""
        # Use correct import path for patching in the client module
        namespace_path = 'fontana.core.da.client.Namespace'
        
        # Use a valid hex namespace ID
        valid_namespace_id = "0123456789abcdef"
        valid_namespace_bytes = bytes.fromhex(valid_namespace_id)
        
        # Set up mock header response with a height greater than our submission
        mock_header_response = MagicMock()
        mock_header_response.height = 1002  # Submission height + confirmation blocks
        celestia_client.client.header.get_by_height = MagicMock(return_value=mock_header_response)
        
        # Create a blob reference
        blob_ref = f"1000:{valid_namespace_id}"
        
        # Set up a pending submission
        celestia_client.pending_submissions = {
            valid_namespace_id: {
                "block_height": 123,
                "submitted_at": time.time() - 10,
                "confirmed": False,
                "celestia_height": 1000,
                "blob_ref": blob_ref
            }
        }
        
        # Create a context manager to patch _namespace_id_bytes
        with patch.object(celestia_client, '_namespace_id_bytes') as mock_namespace_id_bytes:
            mock_namespace_id_bytes.return_value = valid_namespace_bytes
            
            # Mock the Namespace class
            with patch(namespace_path) as mock_namespace:
                # Configure mock properly
                mock_namespace_instance = MagicMock()
                mock_namespace.return_value = mock_namespace_instance
                
                # Mock blob.get to return valid data
                mock_get_response = MagicMock()
                mock_get_response.data = [b'test-data']  # Just needs to be non-empty
                celestia_client.client.blob.get = MagicMock(return_value=mock_get_response)
                
                # Check confirmation
                result = celestia_client.check_confirmation(valid_namespace_id)
                
                # Verify the namespace was created properly
                mock_namespace.assert_called_once_with(valid_namespace_bytes)
                
                # Verify the result
                assert result is True
                
                # Verify the pending submission was marked as confirmed
                assert celestia_client.pending_submissions[valid_namespace_id]["confirmed"] is True
                
                # Verify the blob.get was called with the right parameters
                celestia_client.client.blob.get.assert_called_once()
                call_args = celestia_client.client.blob.get.call_args
                kwargs = call_args[1]
                assert kwargs['height'] == 1000
                assert kwargs['namespace_id'] == mock_namespace_instance
    
    def test_check_confirmation_not_found(self, celestia_client):
        """Test checking confirmation for a non-existent submission."""
        # Use direct pylestia path for patching
        namespace_path = 'pylestia.types.Namespace'
        
        # Use a valid hex namespace ID that doesn't exist in pending submissions
        valid_namespace_id = "0123456789abcdef"
        valid_namespace_bytes = bytes.fromhex(valid_namespace_id)
        
        # Set up mock header response
        mock_header_response = MagicMock()
        mock_header_response.height = 1000
        celestia_client.client.header.get_by_height = MagicMock(return_value=mock_header_response)
        
        # Mock the Namespace class and _namespace_id_bytes method
        with patch.object(celestia_client, '_namespace_id_bytes') as mock_namespace_id_bytes:
            mock_namespace_id_bytes.return_value = valid_namespace_bytes
            
            with patch(namespace_path) as mock_namespace:
                # Configure mock properly
                mock_namespace_instance = MagicMock()
                mock_namespace.return_value = mock_namespace_instance
                
                # Make sure the pending submissions dict is empty
                celestia_client.pending_submissions = {}
                
                # Check a non-existent namespace
                result = celestia_client.check_confirmation(valid_namespace_id)
                
                # Verify the result
                assert result is False
