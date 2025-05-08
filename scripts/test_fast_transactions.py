#!/usr/bin/env python
"""
Test script for fast transaction processing with efficient batching.

This script demonstrates the sub-100ms transaction processing capability
by sending multiple transactions in rapid succession while measuring response times.
"""
import time
import argparse
import logging
import json
import subprocess
from typing import Dict, List, Any, Optional
import statistics

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("fast_tx_test")

def run_cli_command(command: List[str]) -> Dict[str, Any]:
    """Run a CLI command and return JSON output."""
    try:
        start_time = time.time()
        cmd = ["python", "-m", "fontana.cli"] + command
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        response_time = int((time.time() - start_time) * 1000)
        
        try:
            json_result = json.loads(result.stdout)
            json_result["cli_response_time_ms"] = response_time
            return json_result
        except json.JSONDecodeError:
            logger.debug(f"Raw output (not JSON): {result.stdout}")
            return {"output": result.stdout, "cli_response_time_ms": response_time}
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e.stderr}")
        return {"error": e.stderr}

def get_wallet_address(name: str) -> str:
    """Get the address of a wallet."""
    result = run_cli_command(["wallet", "address", "--name", name])
    return result.get("address", "")

def send_transaction(from_wallet: str, to_address: str, amount: float) -> Dict[str, Any]:
    """Send a transaction and measure response time."""
    start_time = time.time()
    result = run_cli_command([
        "wallet", "send",
        "--from-wallet", from_wallet,
        "--to", to_address,
        "--amount", str(amount)
    ])
    total_time = int((time.time() - start_time) * 1000)
    result["total_time_ms"] = total_time
    return result

def main():
    parser = argparse.ArgumentParser(description="Test fast transaction processing")
    parser.add_argument("--sender", default="alice", help="Sender wallet name")
    parser.add_argument("--receiver", default="bob", help="Receiver wallet name")
    parser.add_argument("--count", type=int, default=5, help="Number of transactions to send")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between transactions in seconds")
    parser.add_argument("--amount", type=float, default=0.1, help="Amount to send in each transaction")
    args = parser.parse_args()

    # Get receiver address
    receiver_address = get_wallet_address(args.receiver)
    if not receiver_address:
        logger.error(f"Could not get address for wallet: {args.receiver}")
        return

    logger.info(f"Sending {args.count} transactions from {args.sender} to {args.receiver}")
    logger.info(f"Receiver address: {receiver_address}")
    
    # Send multiple transactions rapidly and collect timing data
    response_times = []
    for i in range(args.count):
        logger.info(f"Sending transaction {i+1}/{args.count}")
        result = send_transaction(args.sender, receiver_address, args.amount)
        
        if "error" in result:
            logger.error(f"Transaction failed: {result['error']}")
            continue
            
        response_time = result.get("cli_response_time_ms", 0)
        response_times.append(response_time)
        
        logger.info(f"Transaction {i+1} response time: {response_time}ms")
        
        if i < args.count - 1:
            time.sleep(args.delay)  # Small delay between transactions
    
    # Calculate statistics
    if response_times:
        avg_response = statistics.mean(response_times)
        min_response = min(response_times)
        max_response = max(response_times)
        
        logger.info(f"\nTransaction Response Time Statistics:")
        logger.info(f"Average response time: {avg_response:.2f} ms")
        logger.info(f"Minimum response time: {min_response} ms")
        logger.info(f"Maximum response time: {max_response} ms")
        logger.info(f"Number of sub-100ms responses: {sum(1 for t in response_times if t < 100)}/{len(response_times)}")

if __name__ == "__main__":
    main()
