#!/usr/bin/env python3
"""
Fontana Rollup Node Runner

This script starts a complete Fontana rollup node that:
1. Initializes the ledger with the genesis state
2. Sets up a transaction processor 
3. Creates a block generator
4. Processes transactions and creates blocks
5. Submits blocks to Celestia DA layer

Usage:
    python run_node.py [--rpc-port PORT] [--force-init] [--genesis PATH]
"""

import os
import sys
import time
import logging
import argparse
import signal
import threading
import dotenv
from pathlib import Path
from typing import Dict, Any, Optional

# Add the project root to the path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from fontana.core.config import config, load_config_from_env
from fontana.core.db import db
from fontana.core.ledger import Ledger
from fontana.core.block_generator.processor import TransactionProcessor
from fontana.core.block_generator.generator import BlockGenerator
from fontana.core.notifications import NotificationManager
from fontana.core.da import CelestiaClient
from fontana.core.models.genesis import GenesisState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("fontana-node")

# Global variables
running = True
block_generator = None

def signal_handler(sig, frame):
    """Handle interrupt signals to gracefully shut down the node."""
    global running, block_generator
    logger.info("Shutting down node...")
    running = False
    if block_generator and block_generator.is_running:
        block_generator.stop()
    time.sleep(1)  # Give threads time to clean up
    sys.exit(0)

def load_genesis_file(file_path: str) -> GenesisState:
    """Load the genesis state from a JSON file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Genesis file not found: {file_path}")
    
    logger.info(f"Loading genesis state from {file_path}")
    try:
        # Import here to avoid circular imports
        from scripts.create_genesis import load_genesis_file as load_genesis
        return load_genesis(file_path)
    except Exception as e:
        logger.error(f"Failed to load genesis file: {str(e)}")
        raise

def initialize_ledger(genesis_file: str, force: bool = False) -> bool:
    """Initialize the ledger with the genesis state."""
    # Check if database already exists
    if os.path.exists(config.db_path) and not force:
        logger.info(f"Database already exists at {config.db_path}, skipping initialization")
        return True
    
    logger.info(f"Initializing ledger with genesis file: {genesis_file}")
    try:
        # Import here to avoid circular imports
        from scripts.create_genesis import initialize_ledger as init_ledger
        init_ledger(genesis_file)
        logger.info("Ledger initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize ledger: {str(e)}")
        return False

def create_celestia_client() -> CelestiaClient:
    """Create a Celestia client for DA submissions."""
    # Get Celestia settings from environment
    celestia_node_url = os.environ.get("CELESTIA_NODE_URL")
    auth_token = os.environ.get("CELESTIA_AUTH_TOKEN", "")
    namespace_id = os.environ.get("CELESTIA_NAMESPACE_ID", "fontana")
    
    # Log current Celestia settings
    logger.info(f"Celestia Settings:")
    logger.info(f"  CELESTIA_NODE_URL: {celestia_node_url}")
    logger.info(f"  CELESTIA_AUTH_TOKEN: {'<SET>' if auth_token else '<NOT SET>'}")
    logger.info(f"  CELESTIA_NAMESPACE_ID: {namespace_id}")
    
    if not celestia_node_url:
        logger.error("CELESTIA_NODE_URL not set in environment - required for rollup node!")
        raise ValueError("CELESTIA_NODE_URL must be set to run the rollup node")
    
    try:
        # Create a custom notification manager for the client
        notification_manager = NotificationManager()
        
        # The config system uses FONTANA_* prefixed environment variables
        # Map our CELESTIA_* variables to the expected FONTANA_* format
        os.environ["FONTANA_CELESTIA_NODE_URL"] = celestia_node_url
        os.environ["FONTANA_CELESTIA_AUTH_TOKEN"] = auth_token
        os.environ["FONTANA_CELESTIA_NAMESPACE"] = namespace_id  # Note: NAMESPACE not NAMESPACE_ID
        
        logger.info("Setting Fontana config system environment variables:")
        logger.info(f"  FONTANA_CELESTIA_NODE_URL: {celestia_node_url}")
        logger.info(f"  FONTANA_CELESTIA_AUTH_TOKEN: <SET>")
        logger.info(f"  FONTANA_CELESTIA_NAMESPACE: {namespace_id}")
        
        # The load_config_from_env() function returns a new config object but doesn't update the global one
        # We need to directly modify the global config object
        logger.info("Directly updating global config object")
        config.celestia_node_url = celestia_node_url
        config.celestia_auth_token = auth_token
        config.celestia_namespace = namespace_id
        
        # Now create the client with our notification manager
        client = CelestiaClient(notification_manager)
        
        # Verify the client was initialized correctly using the public property
        if not client.is_initialized or not client.client:
            logger.error("Celestia client failed to initialize - check CELESTIA_NODE_URL and AUTH_TOKEN")
            raise ValueError("Celestia client failed to initialize")
            
        logger.info("Celestia client created successfully")
        return client
    except Exception as e:
        logger.error(f"Failed to create Celestia client: {str(e)}")
        raise RuntimeError(f"Failed to initialize Celestia client: {str(e)}")

def load_dotenv():
    """Load environment variables from .env file and report which file was loaded."""
    # Try to load .env file from the project root directory
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    
    if env_path.exists():
        logger.info(f"Loading environment variables from: {env_path}")
        dotenv.load_dotenv(env_path)
        return True
    else:
        logger.warning(f"No .env file found at {env_path}")
        return False

def log_environment_variables():
    """Log all Fontana-related environment variables for debugging."""
    fontana_vars = {
        "ROLLUP_DB_PATH": os.environ.get("ROLLUP_DB_PATH"),
        "VAULT_WATCHER_DB": os.environ.get("VAULT_WATCHER_DB"),
        "CELESTIA_NODE_URL": os.environ.get("CELESTIA_NODE_URL"),
        "CELESTIA_AUTH_TOKEN": "<SET>" if os.environ.get("CELESTIA_AUTH_TOKEN") else "<NOT SET>",
        "CELESTIA_NAMESPACE_ID": os.environ.get("CELESTIA_NAMESPACE_ID"),
        "L1_VAULT_ADDRESS": os.environ.get("L1_VAULT_ADDRESS"),
        "GENESIS_PRIVATE_KEY": "<SET>" if os.environ.get("GENESIS_PRIVATE_KEY") else "<NOT SET>",
        "GENESIS_FILE": os.environ.get("GENESIS_FILE"),
        "BLOCK_TIME": os.environ.get("BLOCK_TIME"),
        "MAX_TRANSACTIONS_PER_BLOCK": os.environ.get("MAX_TRANSACTIONS_PER_BLOCK"),
        "MINIMUM_FEE": os.environ.get("MINIMUM_FEE"),
        "RPC_PORT": os.environ.get("RPC_PORT"),
    }
    
    logger.info("=== Fontana Environment Variables ===")
    for var_name, var_value in fontana_vars.items():
        logger.info(f"  {var_name}: {var_value}")
    logger.info("=======================================")


def run_node(args):
    """Run the Fontana rollup node."""
    global running, block_generator
    
    # First, try to load .env file
    dotenv_loaded = load_dotenv()
    if not dotenv_loaded:
        logger.warning("No .env file found, proceeding with environment variables only")
    
    # Log all environment variables for debugging
    log_environment_variables()
    
    # Load configuration from environment
    load_config_from_env()    
    
    # Get configuration from environment variables
    block_interval = int(os.environ.get("BLOCK_TIME", 15))
    max_transactions = int(os.environ.get("MAX_TRANSACTIONS_PER_BLOCK", 1000))
    minimum_fee = float(os.environ.get("MINIMUM_FEE", 0.01))
    fee_schedule_id = "default"
    
    # Get RPC port from environment or command line args
    rpc_port = args.rpc_port if args.rpc_port else int(os.environ.get("RPC_PORT", 8545))
    
    # Set database path - IMPORTANT: prioritize explicitly set ROLLUP_DB_PATH
    db_path = os.environ.get("ROLLUP_DB_PATH")
    if not db_path:
        # Fall back to default path only if ROLLUP_DB_PATH is not set
        db_path = "./data/rollup.db"
        logger.info("ROLLUP_DB_PATH not set, using default path")
    
    # Ensure path is absolute
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.getcwd(), db_path)
    logger.info(f"Using database at: {db_path}")
    
    # Make sure the database directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # Set DB_PATH in environment to ensure it's used
    os.environ["ROLLUP_DB_PATH"] = db_path
    
    # Initialize the ledger if needed
    genesis_file = args.genesis or os.environ.get("GENESIS_FILE", "examples/custom_genesis.json")
    if args.force_init or not os.path.exists(db_path):
        # Temporarily set the db_path in environment for initialization
        os.environ["ROLLUP_DB_PATH"] = db_path
        if not initialize_ledger(genesis_file, args.force_init):
            logger.error("Failed to initialize ledger, exiting")
            return 1
    
    # Create ledger instance
    logger.info("Creating ledger instance")
    ledger = Ledger()
    
    # Create notification manager
    logger.info("Creating notification manager")
    notification_manager = NotificationManager()
    
    # Create transaction processor
    logger.info("Creating transaction processor")
    processor = TransactionProcessor(ledger, notification_manager)
    
    # Create Celestia client for DA submissions
    celestia_client = create_celestia_client()
    
    # Create block generator with our custom settings
    logger.info("Creating block generator")
    block_generator = BlockGenerator(
        ledger=ledger,
        processor=processor,
        notification_manager=notification_manager,
        celestia_client=celestia_client
    )
    
    # Manually set block generator properties
    block_generator.block_interval = block_interval
    block_generator.max_block_size = max_transactions
    
    # Manually set transaction processor properties
    processor.minimum_fee = minimum_fee
    
    # Create a web server for RPC in a separate thread if needed
    # This would interact with the transaction processor for submitting transactions
    # and with the ledger for querying state
    # For now, we'll just print a message
    logger.info(f"RPC server would start on port {rpc_port} (not implemented yet)")
    
    # Start the block generator
    logger.info("Starting block generator")
    block_generator.start()
    
    # Main loop
    logger.info("Node is running. Press Ctrl+C to exit.")
    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    finally:
        if block_generator and block_generator.is_running:
            logger.info("Stopping block generator")
            block_generator.stop()
    
    logger.info("Node shutdown complete")
    return 0

def main():
    """Main entry point."""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Fontana Rollup Node")
    parser.add_argument("--rpc-port", type=int, help="RPC server port")
    parser.add_argument("--force-init", action="store_true", help="Force ledger initialization")
    parser.add_argument("--genesis", help="Path to genesis file")
    args = parser.parse_args()
    
    # Run the node
    sys.exit(run_node(args))

if __name__ == "__main__":
    main()
