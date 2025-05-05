"""
Command-line interface for the Fontana Blob Poster daemon.

This script provides a CLI for starting and managing the Blob Poster daemon,
which posts blocks to the Celestia Data Availability layer.
"""
import time
import signal
import logging
import sys
from typing import Optional

import typer

from fontana.core.config import config
from fontana.core.da.client import CelestiaClient
from fontana.core.da.poster import BlobPoster
from fontana.core.notifications import NotificationManager, NotificationType

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("fontana.blob_poster")

# Create Typer app
app = typer.Typer(help="Fontana Blob Poster daemon")

# Global reference to the poster for signal handling
poster: Optional[BlobPoster] = None


def signal_handler(sig, frame):
    """Handle signals for graceful shutdown."""
    logger.info("Received shutdown signal, stopping Blob Poster daemon...")
    if poster:
        poster.stop()
    sys.exit(0)


@app.command()
def run(
    poll_interval: int = typer.Option(2, help="Seconds to wait between polling for new blocks"),
    max_retries: int = typer.Option(3, help="Maximum number of retries for failed submissions"),
    backoff_factor: float = typer.Option(1.5, help="Backoff multiplier for retry delays"),
    notifications: bool = typer.Option(True, help="Enable or disable notifications")
):
    """Run the Blob Poster daemon.
    
    This command starts the Blob Poster daemon, which watches for new blocks
    in the database and posts them to the Celestia Data Availability layer.
    """
    global poster
    
    logger.info("Starting Fontana Blob Poster daemon")
    logger.info(f"Configuration: poll_interval={poll_interval}s, max_retries={max_retries}, backoff={backoff_factor}")
    
    # Check Celestia configuration
    if not config.celestia_node_url or not config.celestia_auth_token:
        logger.warning("Celestia configuration is incomplete, daemon will run in mock mode")
    
    # Initialize notification manager if enabled
    notification_manager = None
    if notifications:
        logger.info("Initializing notification manager")
        notification_manager = NotificationManager()
    
    # Initialize Celestia client
    celestia_client = CelestiaClient(notification_manager)
    
    # Initialize and start the poster
    poster = BlobPoster(
        celestia_client=celestia_client,
        notification_manager=notification_manager,
        poll_interval=poll_interval,
        max_retries=max_retries,
        backoff_factor=backoff_factor
    )
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start the poster
        poster.start()
        logger.info("Blob Poster daemon is running. Press Ctrl+C to stop.")
        
        # Keep the main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, stopping daemon...")
        poster.stop()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error in Blob Poster daemon: {str(e)}")
        if poster:
            poster.stop()
        sys.exit(1)


if __name__ == "__main__":
    app()
