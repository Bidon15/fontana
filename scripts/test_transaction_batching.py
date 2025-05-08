#!/usr/bin/env python3
"""
Test transaction batching with multiple sends.

This script creates a series of small transactions to demonstrate how
the batching system works. It helps verify that:
1. UTXOs are correctly tracked and not double-spent
2. Transactions are properly batched for block generation
3. The CLI feedback provides useful information about batch status

Usage:
    python scripts/test_transaction_batching.py
"""

import os
import time
import argparse
import subprocess
from typing import List, Optional

def parse_arguments():
    parser = argparse.ArgumentParser(description="Test transaction batching")
    parser.add_argument(
        "--from-wallet", 
        type=str, 
        default="sender",
        help="Name of the wallet to send from"
    )
    parser.add_argument(
        "--to-wallet", 
        type=str, 
        default="receiver",
        help="Name of the wallet to send to"
    )
    parser.add_argument(
        "--count", 
        type=int, 
        default=5,
        help="Number of transactions to send"
    )
    parser.add_argument(
        "--amount", 
        type=float, 
        default=0.1,
        help="Amount per transaction"
    )
    parser.add_argument(
        "--delay", 
        type=float, 
        default=0.5,
        help="Delay between transactions in seconds"
    )
    return parser.parse_args()

def get_wallet_address(wallet_name: str) -> Optional[str]:
    """Get the address of a wallet by name."""
    try:
        result = subprocess.run(
            ["fontana", "wallet", "address", "--name", wallet_name],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Error getting address for wallet {wallet_name}: {result.stderr}")
            return None
            
        # Parse the address from the output (typically shows as "👛 Address: <address>")
        for line in result.stdout.splitlines():
            if "Address:" in line:
                return line.split("Address:", 1)[1].strip()
                
        return None
    except Exception as e:
        print(f"Failed to get wallet address: {str(e)}")
        return None

def ensure_wallet_exists(wallet_name: str) -> bool:
    """Check if wallet exists, create it if it doesn't."""
    # Try to get the address, which will fail if the wallet doesn't exist
    address = get_wallet_address(wallet_name)
    if address:
        print(f"Wallet {wallet_name} exists with address {address}")
        return True
    
    # Create the wallet if it doesn't exist
    try:
        result = subprocess.run(
            ["fontana", "wallet", "create", "--name", wallet_name],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Error creating wallet {wallet_name}: {result.stderr}")
            return False
        
        print(f"Created new wallet {wallet_name}")
        return True
    except Exception as e:
        print(f"Failed to create wallet: {str(e)}")
        return False

def send_transaction(from_wallet: str, to_address: str, amount: float, fee: float = 0.01) -> bool:
    """Send a transaction and return whether it was successful."""
    try:
        cmd = [
            "fontana", "wallet", "send", 
            to_address, 
            str(amount), 
            "--fee", str(fee),
            "--from-wallet", from_wallet
        ]
        
        print(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Transaction failed: {result.stderr}")
            print(result.stdout)
            return False
        
        print(result.stdout)
        return True
    except Exception as e:
        print(f"❌ Error sending transaction: {str(e)}")
        return False

def check_wallet_balance(wallet_name: str) -> Optional[float]:
    """Get the balance of a wallet."""
    try:
        result = subprocess.run(
            ["fontana", "wallet", "balance", "--name", wallet_name],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Error checking balance for {wallet_name}: {result.stderr}")
            return None
            
        # Parse the balance from the output
        for line in result.stdout.splitlines():
            if "Balance:" in line:
                balance_str = line.split("Balance:", 1)[1].strip()
                try:
                    # Remove any 'TIA' or other currency indicators and convert to float
                    balance_str = balance_str.split()[0].strip()
                    return float(balance_str)
                except (ValueError, IndexError):
                    print(f"Could not parse balance from: {line}")
                    return None
                
        print(f"Could not find balance in output: {result.stdout}")
        return None
    except Exception as e:
        print(f"Failed to check balance: {str(e)}")
        return None

def list_utxos(wallet_name: str) -> None:
    """List UTXOs for a wallet."""
    try:
        result = subprocess.run(
            ["fontana", "wallet", "list-utxos", "--name", wallet_name],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Error listing UTXOs for {wallet_name}: {result.stderr}")
            return
            
        print(f"\n--- UTXOs for {wallet_name} ---")
        print(result.stdout)
    except Exception as e:
        print(f"Failed to list UTXOs: {str(e)}")

def main():
    args = parse_arguments()
    
    # Make sure both wallets exist
    if not ensure_wallet_exists(args.from_wallet) or not ensure_wallet_exists(args.to_wallet):
        print("Failed to ensure wallets exist")
        return
    
    # Get addresses
    from_address = get_wallet_address(args.from_wallet)
    to_address = get_wallet_address(args.to_wallet)
    
    if not from_address or not to_address:
        print("Failed to get wallet addresses")
        return
    
    # Check initial balances
    print("\n=== Initial State ===")
    sender_balance = check_wallet_balance(args.from_wallet)
    receiver_balance = check_wallet_balance(args.to_wallet)
    
    if sender_balance is None:
        print(f"Couldn't get balance for {args.from_wallet}")
        return
        
    print(f"Sender ({args.from_wallet}) balance: {sender_balance}")
    print(f"Receiver ({args.to_wallet}) balance: {receiver_balance or 0}")
    
    # List initial UTXOs
    list_utxos(args.from_wallet)
    
    # Calculate if we have enough funds
    total_needed = args.count * (args.amount + 0.01)  # amount + fee
    if sender_balance < total_needed:
        print(f"⚠️ Warning: Sender balance {sender_balance} may not be enough for {args.count} transactions of {args.amount} + fee")
        choice = input("Continue anyway? (y/n): ")
        if choice.lower() != 'y':
            return
    
    # Send transactions
    print(f"\n=== Sending {args.count} transactions of {args.amount} TIA each ===")
    print(f"From: {args.from_wallet} ({from_address})")
    print(f"To: {args.to_wallet} ({to_address})")
    print(f"Delay between transactions: {args.delay} seconds")
    print("Starting in 3 seconds...")
    time.sleep(3)
    
    successful = 0
    for i in range(args.count):
        print(f"\n--- Transaction {i+1}/{args.count} ---")
        if send_transaction(args.from_wallet, to_address, args.amount):
            successful += 1
        
        # Wait before next transaction
        if i < args.count - 1:
            time.sleep(args.delay)
    
    # Final report
    print(f"\n=== Batch Test Complete ===")
    print(f"Successfully sent {successful}/{args.count} transactions")
    print(f"Total amount sent: {successful * args.amount} TIA")
    print(f"Total fees: {successful * 0.01} TIA")
    
    # Check final balances after waiting for processing
    print("\nWaiting 10 seconds for transaction processing...")
    time.sleep(10)
    
    print("\n=== Final State ===")
    final_sender = check_wallet_balance(args.from_wallet)
    final_receiver = check_wallet_balance(args.to_wallet)
    
    print(f"Sender ({args.from_wallet}) balance: {final_sender}")
    print(f"Receiver ({args.to_wallet}) balance: {final_receiver}")
    
    # Show balance changes
    if sender_balance is not None and final_sender is not None:
        print(f"Sender balance change: {final_sender - sender_balance}")
    if receiver_balance is not None and final_receiver is not None:
        print(f"Receiver balance change: {final_receiver - receiver_balance}")
    
    # Final UTXO state
    list_utxos(args.from_wallet)
    list_utxos(args.to_wallet)

if __name__ == "__main__":
    main()
