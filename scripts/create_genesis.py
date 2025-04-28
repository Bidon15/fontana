#!/usr/bin/env python
"""
Create genesis state for Fontana ledger.

This script initializes the database with the genesis state defined
in a JSON file, creating the initial UTXOs and Block 0.
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import the fontana package
sys.path.append(str(Path(__file__).resolve().parent.parent))

from fontana.core.config import config, load_config_from_env
from fontana.core.db import db
from fontana.core.models.genesis import GenesisState
from fontana.core.models.utxo import UTXO
from fontana.core.models.block import Block, BlockHeader


def load_genesis_file(file_path: str) -> GenesisState:
    """Load the genesis state from a JSON file.
    
    Args:
        file_path: Path to the genesis JSON file
        
    Returns:
        GenesisState: The parsed genesis state
    """
    with open(file_path, 'r') as f:
        data = json.load(f)
    return GenesisState.from_dict(data)


def create_genesis_block(genesis_state: GenesisState) -> Block:
    """Create the genesis block (block 0) from the genesis state.
    
    Args:
        genesis_state: The genesis state
        
    Returns:
        Block: The genesis block
    """
    # Create the block header
    header = BlockHeader(
        height=0,
        prev_hash="0" * 64,  # Genesis block has no previous block
        state_root=genesis_state.initial_state_root,
        timestamp=genesis_state.timestamp,
        tx_count=0,  # No transactions in genesis block
        blob_ref="genesis",  # Special marker for genesis block
        fee_schedule_id=config.fee_schedule_id
    )
    
    # Create the block
    return Block(
        header=header,
        transactions=[]  # No transactions in genesis block
    )


def create_genesis_utxos(genesis_state: GenesisState) -> list[UTXO]:
    """Create UTXOs from the genesis state.
    
    Args:
        genesis_state: The genesis state
        
    Returns:
        list[UTXO]: The list of UTXOs to create
    """
    utxos = []
    for i, utxo_def in enumerate(genesis_state.utxos):
        utxo = UTXO(
            txid="genesis",  # Special marker for genesis transactions
            output_index=i,
            recipient=utxo_def.recipient,
            amount=utxo_def.amount,
            status="unspent"
        )
        utxos.append(utxo)
    return utxos


def initialize_ledger(genesis_file: str):
    """Initialize the ledger with the genesis state.
    
    Args:
        genesis_file: Path to the genesis JSON file
    """
    # Load configuration from environment
    global config
    config = load_config_from_env()
    
    # Load genesis state
    genesis_state = load_genesis_file(genesis_file)
    
    # Initialize database
    db.init_db()
    
    # Create genesis UTXOs
    utxos = create_genesis_utxos(genesis_state)
    for utxo in utxos:
        db.insert_utxo(utxo)
    
    # Create and insert genesis block
    genesis_block = create_genesis_block(genesis_state)
    db.insert_block(genesis_block)
    
    # Mark the genesis block as committed
    db.mark_block_committed(genesis_block.header.height, genesis_block.header.blob_ref)
    
    print(f"Successfully initialized ledger with genesis state.")
    print(f"- Created block 0 with state root: {genesis_state.initial_state_root}")
    print(f"- Created {len(utxos)} UTXOs")
    total_tia = sum(utxo.amount for utxo in utxos)
    print(f"- Total TIA: {total_tia}")


def main():
    parser = argparse.ArgumentParser(description="Initialize Fontana ledger with genesis state")
    parser.add_argument("genesis_file", help="Path to the genesis JSON file")
    parser.add_argument("--force", action="store_true", help="Force reinitialization even if database exists")
    
    args = parser.parse_args()
    
    # Check if the database already exists
    if os.path.exists(config.db_path) and not args.force:
        print(f"Error: Database already exists at {config.db_path}")
        print(f"Use --force to reinitialize the database")
        sys.exit(1)
    
    # Initialize the ledger
    initialize_ledger(args.genesis_file)


if __name__ == "__main__":
    main()
