#!/usr/bin/env python3
"""
Create a genesis wallet that has access to the initial funds in the Fontana rollup.

This script:
1. Generates a deterministic wallet with a known private key
2. Saves it as 'genesis' wallet
3. Creates a new genesis.json file with this wallet address funded

Usage:
    python create_genesis_wallet.py [--update-genesis] [--name NAME] [--force]
"""

import os
import json
import base64
import argparse
import sys
from pathlib import Path

# Add the project root to the path for imports
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from fontana.wallet.wallet import Wallet
from nacl.signing import SigningKey
from nacl.encoding import Base64Encoder

def create_genesis_wallet(name="genesis", force=False, update_genesis=False):
    """Create a deterministic 'genesis' wallet for testing."""
    # Define a fixed private key for the genesis wallet
    # This is for TESTING only and should never be used in production
    genesis_private_key = bytes.fromhex("1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef")
    
    # Create a wallet directory if it doesn't exist
    wallet_dir = os.path.expanduser("~/.fontana")
    os.makedirs(wallet_dir, exist_ok=True)
    
    # Define the wallet path
    wallet_path = os.path.join(wallet_dir, f"{name}.json")
    
    # Check if wallet exists and handle force option
    if os.path.exists(wallet_path) and not force:
        print(f"⚠️  Wallet '{name}' already exists at {wallet_path}")
        print(f"Use --force to overwrite the existing wallet.")
        return
    
    # Create the wallet with the fixed private key
    signing_key = SigningKey(genesis_private_key)
    wallet = Wallet(signing_key)
    
    # Save the wallet
    with open(wallet_path, "w") as f:
        json.dump({
            "private_key": base64.b64encode(signing_key.encode()).decode("utf-8")
        }, f)
    
    # Get the wallet address
    address = wallet.get_address()
    print(f"✅ Genesis wallet '{name}' created at {wallet_path}")
    print(f"👛 Address: {address}")
    
    # Read genesis.json to check if this address is in the initial UTXOs
    genesis_path = os.path.join(project_root, "examples", "genesis.json")
    if os.path.exists(genesis_path):
        with open(genesis_path, "r") as f:
            genesis_data = json.load(f)
        
        # Check if the address is in the initial UTXOs
        found = False
        if "utxos" in genesis_data:
            for utxo in genesis_data["utxos"]:
                if utxo.get("recipient") == address:
                    print(f"✅ Address found in genesis.json with {utxo.get('amount')} tokens!")
                    found = True
                    break
        
        if not found and update_genesis:
            print(f"⚠️  Address not found in genesis.json. Creating a new genesis file with this address funded.")
            
            # Create a new genesis.json with our wallet address funded
            custom_genesis_path = os.path.join(project_root, "examples", "custom_genesis.json")
            
            # Update the UTXOs to include our address
            genesis_data["utxos"] = [
                {
                    "recipient": address,
                    "amount": 1000.0
                }
            ]
            
            # Write the new genesis file
            with open(custom_genesis_path, "w") as f:
                json.dump(genesis_data, f, indent=2)
            
            print(f"✅ Created custom genesis file at {custom_genesis_path}")
            print(f"⚠️  To use this genesis file, run: \n   poetry run python -m fontana.node --init --genesis {custom_genesis_path}")
        elif not found:
            print("⚠️  Address not found in genesis.json. This wallet may not have initial funds.")
            print(f"Run this script with --update-genesis to create a new genesis file with this address funded.")
            
            # Print all available UTXOs in genesis for reference
            print("\nAvailable UTXOs in genesis.json:")
            for i, utxo in enumerate(genesis_data.get("utxos", [])):
                print(f"  {i+1}. Recipient: {utxo.get('recipient')}, Amount: {utxo.get('amount')}")

def main():
    parser = argparse.ArgumentParser(description="Create a genesis wallet for testing")
    parser.add_argument("--name", default="genesis", help="Name for the wallet (default: genesis)")
    parser.add_argument("--force", action="store_true", help="Force overwrite if wallet exists")
    parser.add_argument("--update-genesis", action="store_true", help="Create a new genesis.json file with this wallet address funded")
    
    args = parser.parse_args()
    create_genesis_wallet(args.name, args.force, args.update_genesis)

if __name__ == "__main__":
    main()
