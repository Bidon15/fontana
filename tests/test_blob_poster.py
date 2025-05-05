"""
Tests for the Blob Poster daemon.
"""
import pytest
import json
import time
from unittest.mock import MagicMock, patch, call

from fontana.core.da.poster import BlobPoster
from fontana.core.da.client import CelestiaClient, CelestiaSubmissionError
from fontana.core.models.block import Block, BlockHeader
from fontana.core.notifications import NotificationManager, NotificationType


@pytest.fixture
def mock_notification_manager():
    """Create a mock notification manager."""
    manager = MagicMock(spec=NotificationManager)
    return manager


@pytest.fixture
def mock_celestia_client(mock_notification_manager):
    """Create a mock Celestia client."""
    client = MagicMock(spec=CelestiaClient)
    client.notification_manager = mock_notification_manager
    return client


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
def blob_poster(mock_celestia_client, mock_notification_manager):
    """Create a BlobPoster instance for testing."""
    poster = BlobPoster(
        celestia_client=mock_celestia_client,
        notification_manager=mock_notification_manager,
        poll_interval=0.1,  # Short interval for testing
        max_retries=2,
        backoff_factor=1.2
    )
    return poster


class TestBlobPoster:
    """Tests for the BlobPoster class."""
    
    @patch('fontana.core.da.poster.db')
    def test_fetch_uncommitted_blocks(self, mock_db, blob_poster, mock_block):
        """Test fetching uncommitted blocks from the database."""
        # Set up mock cursor
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn
        
        # Set up cursor to return a serialized block
        mock_cursor.fetchall.return_value = [(json.dumps(mock_block.model_dump()),)]
        
        # Call the method
        blocks = blob_poster.fetch_uncommitted_blocks()
        
        # Verify the SQL query
        mock_cursor.execute.assert_called_with("""
                SELECT json 
                FROM blocks 
                WHERE committed = 0
                ORDER BY height ASC
            """)
        
        # Verify connection was closed
        mock_conn.close.assert_called_once()
        
        # Verify blocks returned
        assert len(blocks) == 1
        assert blocks[0].header.height == mock_block.header.height
        assert blocks[0].header.hash == mock_block.header.hash
    
    @patch('fontana.core.da.poster.db')
    def test_mark_block_committed(self, mock_db, blob_poster):
        """Test marking a block as committed in the database."""
        # Set up mock cursor
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn
        
        # Set up cursor to indicate success (1 row updated)
        mock_cursor.rowcount = 1
        
        # Call the method
        result = blob_poster.mark_block_committed(123, "test-blob-ref")
        
        # Verify the SQL query
        mock_cursor.execute.assert_called_with("""
                UPDATE blocks 
                SET committed = 1, blob_ref = ? 
                WHERE height = ?
            """, ("test-blob-ref", 123))
        
        # Verify commit was called
        mock_conn.commit.assert_called_once()
        
        # Verify connection was closed
        mock_conn.close.assert_called_once()
        
        # Verify notification was sent
        blob_poster.notification_manager.notify.assert_called_with(
            notification_type=NotificationType.BLOCK_COMMITTED_TO_DA,
            block_height=123
        )
        
        # Verify success
        assert result is True
    
    def test_post_block_to_celestia_success(self, blob_poster, mock_block, mock_celestia_client):
        """Test posting a block to Celestia successfully on first try."""
        # Set up mock to return a blob ref
        mock_celestia_client.post_block.return_value = "test-blob-ref"
        
        # Call the method
        result = blob_poster.post_block_to_celestia(mock_block)
        
        # Verify post_block was called with the block
        mock_celestia_client.post_block.assert_called_once_with(mock_block)
        
        # Verify the blob ref was returned
        assert result == "test-blob-ref"
        
        # Verify no retries were made
        assert mock_celestia_client.post_block.call_count == 1
    
    def test_post_block_to_celestia_retry_success(self, blob_poster, mock_block, mock_celestia_client):
        """Test posting a block to Celestia with success after retry."""
        # Set up mock to fail on first call, then succeed
        mock_celestia_client.post_block.side_effect = [
            CelestiaSubmissionError("First attempt failed"),
            "test-blob-ref"
        ]
        
        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            # Call the method
            result = blob_poster.post_block_to_celestia(mock_block)
        
        # Verify post_block was called twice
        assert mock_celestia_client.post_block.call_count == 2
        
        # Verify the blob ref was returned
        assert result == "test-blob-ref"
    
    def test_post_block_to_celestia_max_retries(self, blob_poster, mock_block, mock_celestia_client):
        """Test posting a block to Celestia with max retries reached."""
        # Set up mock to always fail
        mock_celestia_client.post_block.side_effect = CelestiaSubmissionError("Failed")
        
        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            # Call the method
            result = blob_poster.post_block_to_celestia(mock_block)
        
        # Verify post_block was called the expected number of times (1 original + 2 retries)
        assert mock_celestia_client.post_block.call_count == 3
        
        # Verify None was returned
        assert result is None
        
        # Verify the block was added to the retry queue
        assert mock_block.header.height in blob_poster.retry_queue
    
    @patch('fontana.core.da.poster.db')
    def test_process_block_success(self, mock_db, blob_poster, mock_block, mock_celestia_client):
        """Test processing a block successfully."""
        # Set up mocks
        mock_celestia_client.post_block.return_value = "test-blob-ref"
        
        # Mock mark_block_committed to return True
        with patch.object(blob_poster, 'mark_block_committed', return_value=True) as mock_mark:
            # Call the method
            result = blob_poster.process_block(mock_block)
            
            # Verify post_block was called
            mock_celestia_client.post_block.assert_called_once_with(mock_block)
            
            # Verify mark_block_committed was called
            mock_mark.assert_called_once_with(mock_block.header.height, "test-blob-ref")
            
            # Verify success
            assert result is True
    
    @patch('fontana.core.da.poster.db')
    def test_process_block_failure(self, mock_db, blob_poster, mock_block, mock_celestia_client):
        """Test processing a block with Celestia submission failure."""
        # Set up mock to fail
        mock_celestia_client.post_block.side_effect = CelestiaSubmissionError("Failed")
        
        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            # Call the method
            result = blob_poster.process_block(mock_block)
        
        # Verify post_block was called
        mock_celestia_client.post_block.assert_called()
        
        # Verify mark_block_committed was not called
        assert mock_block.header.height in blob_poster.retry_queue
        
        # Verify failure
        assert result is False
    
    def test_process_retry_queue(self, blob_poster, mock_block):
        """Test processing blocks in the retry queue."""
        # Add a block to the retry queue with a past retry time
        blob_poster.retry_queue[123] = {
            "block": mock_block,
            "retry_at": time.time() - 10,  # In the past
            "retry_count": 1
        }
        
        # Mock process_block to succeed
        with patch.object(blob_poster, 'process_block', return_value=True) as mock_process:
            # Call the method
            blob_poster.process_retry_queue()
            
            # Verify process_block was called
            mock_process.assert_called_once_with(mock_block)
            
            # Verify block was removed from retry queue
            assert 123 not in blob_poster.retry_queue
    
    @patch('fontana.core.da.poster.db')
    def test_run_integration(self, mock_db, blob_poster, mock_block, mock_celestia_client):
        """Test the main run loop with integration between components."""
        # Set up mocks
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn
        
        # Set up cursor to return a serialized block, then empty
        mock_cursor.fetchall.side_effect = [
            [(json.dumps(mock_block.model_dump()),)],  # First call returns a block
            []  # Subsequent calls return empty
        ]
        
        # Set up Celestia client to succeed
        mock_celestia_client.post_block.return_value = "test-blob-ref"
        
        # Mock mark_block_committed to return True
        with patch.object(blob_poster, 'mark_block_committed', return_value=True) as mock_mark:
            # Need to stop the run loop after first iteration
            def side_effect():
                blob_poster.is_running = False
                return True
            
            # Set up side effect to stop loop after first iteration
            mock_mark.side_effect = side_effect
            
            # Set blob_poster as running
            blob_poster.is_running = True
            
            # Call the run method
            blob_poster.run()
            
            # Verify fetch_uncommitted_blocks was called
            mock_cursor.execute.assert_called()
            
            # Verify post_block was called
            mock_celestia_client.post_block.assert_called_once_with(mock_block)
            
            # Verify mark_block_committed was called
            mock_mark.assert_called_once_with(mock_block.header.height, "test-blob-ref")
    
    def test_start_stop(self, blob_poster, mock_celestia_client):
        """Test starting and stopping the Blob Poster daemon."""
        # Mock the run method to avoid actually running
        with patch.object(blob_poster, 'run'):
            # Mock threading.Thread
            with patch('threading.Thread') as mock_thread:
                # Start the poster
                blob_poster.start()
                
                # Verify thread was created and started
                mock_thread.assert_called_once()
                mock_thread().start.assert_called_once()
                
                # Verify celestia client monitor was started
                mock_celestia_client.start_monitor.assert_called_once()
                
                # Verify is_running flag
                assert blob_poster.is_running is True
                
                # Stop the poster
                blob_poster.stop()
                
                # Verify is_running flag was reset
                assert blob_poster.is_running is False
                
                # Verify celestia client monitor was stopped
                mock_celestia_client.stop_monitor.assert_called_once()
