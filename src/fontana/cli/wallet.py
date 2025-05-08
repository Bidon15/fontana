"""
Wallet CLI commands for the Fontana rollup.

This module provides real wallet functionality for the Fontana rollup,
including balance queries and transaction creation.
"""

import time
import typer
import os
import hashlib
import json
from typing import List, Optional, Tuple

from fontana.wallet.wallet import Wallet
from fontana.core.ledger import Ledger
from fontana.core.models.transaction import SignedTransaction
from fontana.core.models.utxo import UTXO, UTXORef
from fontana.core.db import db
from fontana.core.config import config
from fontana.core.db.db_extensions import fetch_utxo
import base64

wallet_app = typer.Typer()
DEFAULT_PATH = os.path.expanduser("~/.fontana/wallet.json")


class BatchSessionManager:
    """Manages transaction batching and UTXO chaining for multiple sequential transactions.

    This class tracks virtual UTXOs created by transactions in a batch session and
    allows them to be used as inputs for subsequent transactions, creating a valid
    chain of transactions that can all be included in a single block.
    """

    def __init__(self):
        self.session_utxos = []  # Virtual UTXOs created by transactions in this session
        self.session_txids = []  # TXIDs of transactions in this session
        self.spent_utxo_refs = (
            set()
        )  # Set of "txid:output_index" that have been spent in this session

    def reset(self):
        """Reset the batch session, clearing all tracked UTXOs and TXIDs."""
        self.session_utxos = []
        self.session_txids = []
        self.spent_utxo_refs = set()
        typer.echo("🔄 Batch session reset - chain cleared")

    def add_transaction(self, txid, outputs, inputs=None):
        """Add a transaction's outputs to the session for chaining.

        Args:
            txid: The transaction ID
            outputs: List of UTXO objects created by this transaction
            inputs: Optional list of UTXORef objects used as inputs (to mark as spent)
        """
        self.session_txids.append(txid)
        self.session_utxos.extend(outputs)

        # Mark all inputs as spent to prevent double-spending in this batch
        if inputs:
            for inp in inputs:
                self.spent_utxo_refs.add(f"{inp.txid}:{inp.output_index}")

        # Display info about the UTXOs being tracked
        recipient_counts = {}
        for utxo in self.session_utxos:
            recipient = (
                utxo.recipient[:8] + "..."
                if len(utxo.recipient) > 8
                else utxo.recipient
            )
            if recipient not in recipient_counts:
                recipient_counts[recipient] = 0
            recipient_counts[recipient] += 1

        recipients_str = ", ".join(
            [f"{count} for {recip}" for recip, count in recipient_counts.items()]
        )
        typer.echo(
            f"🔄 Batch session tracking {len(self.session_utxos)} UTXOs ({recipients_str})"
        )

    def get_chained_utxos(self, recipient):
        """Get UTXOs that can be used as inputs for the next transaction in the chain.

        Args:
            recipient: Address to find UTXOs for (usually the sender of the next transaction)

        Returns:
            List of UTXO objects that can be used as inputs
        """
        # Find UTXOs where the recipient matches and that haven't been spent in this session
        available_utxos = []
        for utxo in self.session_utxos:
            # Only include UTXOs that match the recipient and haven't been spent yet
            utxo_ref = f"{utxo.txid}:{utxo.output_index}"
            if utxo.recipient == recipient and utxo_ref not in self.spent_utxo_refs:
                available_utxos.append(utxo)

        # Sort by amount (descending) to use larger UTXOs first
        available_utxos.sort(key=lambda u: u.amount, reverse=True)

        if available_utxos:
            typer.echo(
                f"🔗 Found {len(available_utxos)} chained UTXOs totaling {sum(u.amount for u in available_utxos)} TIA"
            )

        return available_utxos


# Create a singleton instance of the batch session manager
batch_manager = BatchSessionManager()


def get_wallet(name: Optional[str] = None, path: Optional[str] = None) -> Optional[Wallet]:
    """Helper function to load a wallet from name or path.
    
    Args:
        name: Optional wallet name 
        path: Optional path to wallet file
        
    Returns:
        Loaded wallet or None if not found
    """
    if path:
        # Use custom path if provided
        wallet_path = os.path.expanduser(path)
    elif name:
        # Use name-based path in default directory
        wallet_dir = os.path.dirname(DEFAULT_PATH)
        wallet_path = os.path.join(wallet_dir, f"{name}.json")
    else:
        # Use default path
        wallet_path = DEFAULT_PATH

    if not os.path.exists(wallet_path):
        typer.echo(f"❌ Wallet not found at {wallet_path}")
        return None

    try:
        wallet = Wallet.load(wallet_path)
        return wallet
    except Exception as e:
        typer.echo(f"❌ Error loading wallet: {str(e)}")
        return None


def create_transaction(wallet, utxos, recipient, amount, fee, batch_mode=False):
    """Create a real transaction from UTXOs

    Args:
        wallet: Wallet to use for signing
        utxos: List of UTXOs to use as inputs
        recipient: Recipient address
        amount: Amount to send
        fee: Transaction fee
        batch_mode: If True, use UTXO chaining to allow multiple consecutive transactions
    """
    # Get sender address from wallet
    sender = wallet.get_address()

    # Calculate total input amount needed
    total_needed = amount + fee

    # When in batch mode, we need to handle UTXOs differently to ensure we don't double-spend
    if batch_mode:
        # Check if we have any chained UTXOs from previous transactions in this session
        sender_change_utxos = batch_manager.get_chained_utxos(sender)

        if sender_change_utxos:
            typer.echo(
                f"🔗 UTXO CHAINING: Found {len(sender_change_utxos)} change UTXOs from your previous transactions"
            )
            # Add these to our valid UTXOs list first - these are highest priority
            valid_utxos = sender_change_utxos
        else:
            valid_utxos = []
            # Fetch real UTXOs from the database, excluding those in pending transactions
            db_utxos = db.fetch_unspent_utxos(sender, include_pending=False)
            if db_utxos:
                typer.echo(f"💰 Found {len(db_utxos)} available UTXOs from database")
                valid_utxos.extend(db_utxos)
    else:
        # Normal mode - just get UTXOs that aren't referenced in pending transactions
        db_utxos = db.fetch_unspent_utxos(sender, include_pending=False)
        valid_utxos = db_utxos if db_utxos else []
        typer.echo(
            f"Found {len(valid_utxos)} available UTXOs not referenced in pending transactions"
        )

    # Select UTXOs to use as inputs
    inputs = []
    total_input = 0
    used_utxos = []

    # Track which UTXOs we're using to avoid double-spending within this batch
    used_utxo_keys = set()

    for utxo in valid_utxos:
        # Skip already spent UTXOs
        if utxo.is_spent():
            continue

        # In batch mode, we need to also check if we've already used this UTXO in this batch
        utxo_key = f"{utxo.txid}:{utxo.output_index}"
        if batch_mode and utxo_key in used_utxo_keys:
            continue

        inputs.append(UTXORef(txid=utxo.txid, output_index=utxo.output_index))
        total_input += utxo.amount
        used_utxos.append(utxo)
        used_utxo_keys.add(utxo_key)

        if total_input >= total_needed:
            break

    if total_input < total_needed:
        raise ValueError(f"Insufficient funds: have {total_input}, need {total_needed}")

    typer.echo(f"Using {len(inputs)} UTXOs as inputs for this transaction")

    # Create outputs
    outputs = [
        UTXO(
            txid="pending",  # Will be updated after txid is generated
            output_index=0,
            recipient=recipient,
            amount=amount,
            status="unspent",
        )
    ]

    # Add change output if needed
    change = total_input - amount - fee
    if change > 0:
        outputs.append(
            UTXO(
                txid="pending",  # Will be updated after txid is generated
                output_index=1,
                recipient=sender,
                amount=change,
                status="unspent",
            )
        )

    # In batch mode, we'll keep track of these outputs to use in subsequent transactions
    virtual_outputs = outputs.copy()

    # Create payload for signing
    payload = {
        "sender": sender,
        "inputs": [inp.model_dump() for inp in inputs],
        "outputs": [
            {"recipient": out.recipient, "amount": out.amount, "status": out.status}
            for out in outputs
        ],
        "fee": fee,
        "timestamp": int(time.time()),
    }

    # Create txid
    txid = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    # Update output txids
    for i, output in enumerate(outputs):
        output.txid = txid
        output.output_index = i

    # In batch mode, also update the virtual outputs for chaining
    if batch_mode:
        for i, output in enumerate(virtual_outputs):
            output.txid = txid
            output.output_index = i

    # Sign the transaction
    # This is the key fix - we need to create the exact same message format that
    # the ledger validation will use in _validate_signature
    tx_data = {
        "sender": sender,
        "inputs": [inp.model_dump() for inp in inputs],
        "outputs": [
            {"recipient": out.recipient, "amount": out.amount} for out in outputs
        ],
        "fee": fee,
        "timestamp": int(time.time()),
    }
    message = json.dumps(tx_data, sort_keys=True).encode()
    payload_hash = hashlib.sha256(message).hexdigest()

    # Sign with this exact message format
    signature = wallet.sign(message)

    # Create the final transaction
    tx = SignedTransaction(
        txid=txid,
        sender_address=sender,
        inputs=inputs,
        outputs=outputs,
        fee=fee,
        payload_hash=payload_hash,
        timestamp=int(time.time()),
        signature=signature,
    )

    # In batch mode, store these outputs for subsequent transactions
    if batch_mode:
        # Add this transaction's outputs to the batch session manager
        # Also pass the inputs so we can mark them as spent in this session
        batch_manager.add_transaction(txid, virtual_outputs, inputs=inputs)

    return tx


@wallet_app.command("address")
def show_address(
    name: Optional[str] = None,
    path: Optional[str] = None,
):
    """Show the public address of a wallet."""
    if path:
        # Use custom path if provided
        wallet_path = os.path.expanduser(path)
    elif name:
        # Use name-based path in default directory
        wallet_dir = os.path.dirname(DEFAULT_PATH)
        wallet_path = os.path.join(wallet_dir, f"{name}.json")
    else:
        # Use default path
        wallet_path = DEFAULT_PATH

    if not os.path.exists(wallet_path):
        typer.echo(f"❌ Wallet not found at {wallet_path}")
        raise typer.Exit(1)

    wallet = Wallet.load(wallet_path)
    address = wallet.get_address()
    typer.echo(f"👛 Address: {address}")


@wallet_app.command("create")
def create_wallet(
    name: Optional[str] = None,
    path: Optional[str] = None,
):
    """Create a new wallet and save it locally."""
    if path:
        # Use custom path if provided
        wallet_path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(wallet_path), exist_ok=True)
    elif name:
        # Use name-based path in default directory
        wallet_dir = os.path.dirname(DEFAULT_PATH)
        os.makedirs(wallet_dir, exist_ok=True)
        wallet_path = os.path.join(wallet_dir, f"{name}.json")
    else:
        # Use default path
        wallet_path = DEFAULT_PATH
        os.makedirs(os.path.dirname(wallet_path), exist_ok=True)

    if os.path.exists(wallet_path):
        typer.echo(f"⚠️  Wallet already exists at {wallet_path}")
        raise typer.Exit(1)

    wallet = Wallet.generate()
    wallet.save(wallet_path)

    address = wallet.get_address()
    typer.echo(f"✅ Wallet created and saved to {wallet_path}")
    typer.echo(f"🔑 Wallet address: {address}")


@wallet_app.command("balance")
def check_balance(name: Optional[str] = None, path: Optional[str] = None):
    """Check the real balance of a wallet in the ledger."""
    if path:
        # Use custom path if provided
        wallet_path = os.path.expanduser(path)
    elif name:
        # Use name-based path in default directory
        wallet_dir = os.path.dirname(DEFAULT_PATH)
        wallet_path = os.path.join(wallet_dir, f"{name}.json")
    else:
        # Use default path
        wallet_path = DEFAULT_PATH

    if not os.path.exists(wallet_path):
        typer.echo(f"❌ Wallet not found at {wallet_path}")
        raise typer.Exit(1)

    wallet = Wallet.load(wallet_path)
    address = wallet.get_address()

    # Connect to the ledger
    ledger = Ledger()
    balance = ledger.get_balance(address)

    typer.echo(f"💰 Address {address} has balance: {balance} TIA")


def ensure_valid_address(address: str) -> str:
    """Ensure an address is properly formatted for use in the system.

    Base64 encoded addresses must end with '=' padding.
    """
    # Ensure the address ends with '=' for proper base64 encoding
    if not address.endswith("="):
        address = address + "="

    # Normalize the address format
    try:
        # Try to decode and re-encode to normalize format
        decoded = base64.b64decode(address)
        # If successful, return the original address (already valid)
        return address
    except Exception:
        # If we can't decode it, it's not a valid base64 address
        raise ValueError(
            f"Invalid address format: {address}. Must be a valid base64-encoded string."
        )


@wallet_app.command("send")
def send(
    to: str = typer.Argument(..., help="Recipient address"),
    amount: float = typer.Argument(..., help="Amount to send"),
    fee: float = typer.Option(0.01, help="Transaction fee"),
    name: Optional[str] = typer.Option(None, help="Wallet name"),
    path: Optional[str] = typer.Option(None, help="Path to wallet file"),
    batch: bool = typer.Option(
        False, help="Enable batch mode to allow multiple consecutive transactions"
    ),
):
    """Send a real transaction to another address."""
    # Validate and normalize the recipient address
    try:
        to = ensure_valid_address(to)
    except ValueError as e:
        typer.echo(f"❌ {str(e)}")
        raise typer.Exit(1)
    if path:
        # Use custom path if provided
        wallet_path = os.path.expanduser(path)
    elif name:
        # Use name-based path in default directory
        wallet_dir = os.path.dirname(DEFAULT_PATH)
        wallet_path = os.path.join(wallet_dir, f"{name}.json")
    else:
        # Use default path
        wallet_path = DEFAULT_PATH

    if not os.path.exists(wallet_path):
        typer.echo(f"❌ Wallet not found at {wallet_path}")
        raise typer.Exit(1)

    wallet = Wallet.load(wallet_path)
    from_address = wallet.get_address()

    typer.echo(f"🔍 Preparing transaction from {from_address} to {to}")

    # Connect to the ledger for transaction submission
    ledger = Ledger()

    # In batch mode, first check if we have any chained virtual UTXOs from previous transactions
    db_utxos = []
    virtual_utxos = []

    if batch:
        # Get virtual UTXOs from the batch session
        virtual_utxos = batch_manager.get_chained_utxos(from_address)
        if virtual_utxos:
            typer.echo(
                f"🔄 BATCH MODE: Using {len(virtual_utxos)} virtual UTXOs from previous transactions"
            )
            typer.echo(
                f"💰 Total available in virtual UTXOs: {sum(u.amount for u in virtual_utxos)} TIA"
            )
        else:
            typer.echo(
                f"🔄 BATCH MODE ENABLED: No virtual UTXOs available yet, using database UTXOs"
            )

    # Always get UTXOs from the database as a fallback
    # Note: in batch mode we do NOT include pending transactions to avoid double-spending
    db_utxos = db.fetch_unspent_utxos(from_address, include_pending=False)
    if db_utxos:
        typer.echo(f"Found {len(db_utxos)} available UTXOs from database")

    # Combine virtual and database UTXOs
    utxos = virtual_utxos + db_utxos

    if not utxos:
        typer.echo(f"❌ No UTXOs found for address {from_address}")
        raise typer.Exit(1)

    # Display batch mode status if enabled
    if batch:
        typer.echo(f"🔄 BATCH MODE: Will add outputs to the virtual UTXO chain")
        typer.echo(
            f"📝 This allows sending multiple transactions in succession without waiting for block confirmation"
        )

    try:
        # Record start time to measure response speed
        start_time = time.time()

        # Create and sign transaction with the refreshed UTXOs
        # Pass the batch mode parameter to allow for consecutive transactions
        tx = create_transaction(wallet, utxos, to, amount, fee, batch_mode=batch)

        # Display which UTXOs are being used for this transaction
        typer.echo(f"🔗 Using {len(tx.inputs)} UTXOs as inputs:")
        for i, inp in enumerate(tx.inputs, 1):
            typer.echo(f"  {i}. {inp.txid[:8]}...:{inp.output_index}")

        # Fast validation path (sub-100ms)
        # Only do essential validations that can complete very quickly
        if not ledger._validate_signature(tx):
            typer.echo("❌ Transaction has invalid signature")
            raise typer.Exit(1)

        # Do a quick input validation without database lookups
        # This is a fast way to reject obviously invalid transactions
        try:
            # Use a more efficient method to check inputs
            # This avoids expensive database operations during validation
            unique_inputs = set(f"{ref.txid}:{ref.output_index}" for ref in tx.inputs)
            if len(unique_inputs) != len(tx.inputs):
                raise ValueError("Duplicate inputs detected")

            # Check for sufficient funds using in-memory utxos we already have
            # This is faster than fetching them again from the database
            total_input = sum(utxo.amount for utxo in utxos)
            total_output = sum(output.amount for output in tx.outputs) + tx.fee
            if total_input < total_output:
                raise ValueError(f"Insufficient funds: {total_input} < {total_output}")

        except Exception as e:
            typer.echo(f"❌ Transaction validation failed: {str(e)}")
            raise typer.Exit(1)

        # Successfully validated! Insert into database for batching
        db.insert_transaction(tx)

        # If not in batch mode, reset our session tracking to ensure clean state
        if not batch:
            batch_manager.reset()

        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)

        # Create a response including performance metrics
        # Use actual configured block interval instead of hardcoded values
        block_interval = config.block_interval_seconds

        processor_result = {
            "status": "provisionally_accepted",
            "txid": tx.txid,
            "response_time_ms": response_time_ms,
            "estimated_block_time": block_interval,
            "estimated_celestia_time": block_interval,
        }

        # Check the result and display user-friendly output
        if processor_result["status"] == "provisionally_accepted":
            response_time = processor_result.get("response_time_ms", 0)
            est_block_time = processor_result.get("estimated_block_time", 6)
            est_celestia_time = processor_result.get("estimated_celestia_time", 6)

            # Get the current count of pending transactions to show batching progress
            try:
                from fontana.core.block_generator.processor import transaction_processor

                stats = transaction_processor.get_transaction_stats()
                pending_count = stats.get("count", 0)
                batch_size = config.max_transactions_per_block
                batch_progress = f"{pending_count}/{batch_size}"
            except Exception:
                batch_progress = "unknown/unknown"

            typer.echo(f"✅ Transaction {tx.txid} accepted in {response_time}ms")
            typer.echo(f"💸 Sent {amount} TIA to {to} with fee {fee}")
            typer.echo(
                f"🔄 Transaction queued for next block batch ({est_block_time}s)"
            )
            typer.echo(
                f"📡 Celestia DA submission in approximately {est_celestia_time}s"
            )
            typer.echo(f"🔀 Batch progress: {batch_progress} transactions")

            if response_time <= 100:
                typer.echo(
                    f"⚡ Fast transaction processing: {response_time}ms response time"
                )
            else:
                typer.echo(f"⏱️ Transaction processed in: {response_time}ms")

            # Add specific batch mode tip
            if not batch:
                typer.echo(
                    f"📝 TIP: Use --batch flag to send multiple transactions in succession without waiting for confirmation"
                )
            else:
                typer.echo(
                    f"📝 TIP: You can continue sending more transactions with --batch flag until the next block is created"
                )
        else:
            typer.echo(
                f"❌ Transaction rejected: {processor_result.get('reason', 'Unknown reason')}"
            )
            raise typer.Exit(1)

    except ValueError as e:
        typer.echo(f"❌ Error creating transaction: {str(e)}")
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Error processing transaction: {str(e)}")
        raise typer.Exit(1)


@wallet_app.command("list-utxos")
def list_utxos(name: Optional[str] = None, path: Optional[str] = None):
    """List all UTXOs owned by the wallet."""
    if path:
        # Use custom path if provided
        wallet_path = os.path.expanduser(path)
    elif name:
        # Use name-based path in default directory
        wallet_dir = os.path.dirname(DEFAULT_PATH)
        wallet_path = os.path.join(wallet_dir, f"{name}.json")
    else:
        # Use default path
        wallet_path = DEFAULT_PATH

    if not os.path.exists(wallet_path):
        typer.echo(f"❌ Wallet not found at {wallet_path}")
        raise typer.Exit(1)

    wallet = Wallet.load(wallet_path)
    address = wallet.get_address()

    # Connect to the database directly to get UTXOs
    # (The Ledger class doesn't have a get_utxos method)
    utxos = db.fetch_unspent_utxos(address)
    if not utxos:
        typer.echo(f"ℹ️ No UTXOs found for address {address}")
        return

    typer.echo(f"📋 UTXOs for address {address}:")

    total_balance = 0
    for i, utxo in enumerate(utxos, 1):
        status = "✅ Unspent" if not utxo.is_spent() else "❌ Spent"
        typer.echo(
            f"  {i}. {utxo.txid[:8]}...:{utxo.output_index} - {utxo.amount} TIA ({status})"
        )
        if not utxo.is_spent():
            total_balance += utxo.amount

    typer.echo(f"💰 Total unspent: {total_balance} TIA")


@wallet_app.command("batch-test")
def batch_test(
    to: str = typer.Argument(..., help="Recipient address"),
    count: int = typer.Option(3, help="Number of transactions to send"),
    amount: float = typer.Option(0.1, help="Amount to send in each transaction"),
    fee: float = typer.Option(0.01, help="Transaction fee"),
    name: str = typer.Option("", help="Wallet name"),
    path: str = typer.Option("", help="Path to wallet file"),
):
    """Test sending multiple transactions in a batch.

    This command sends multiple transactions together as a single batch.
    It collects all transactions first, then submits them all at once.

    Args:
        to: Recipient address
        count: Number of transactions to send
        amount: Amount to send in each transaction
        fee: Fee for each transaction
        name: Wallet name
        path: Wallet path
    """
    import time
    import typer
    from rich.console import Console
    from fontana.core.config import config
    from fontana.core.ledger import Ledger
    from fontana.core.db import db

    console = Console()

    # Get the wallet
    wallet = get_wallet(name, path)
    if not wallet:
        return

    from_address = wallet.get_address()
    typer.echo(
        f"\n🔍 Batch test: Preparing {count} transactions of {amount} TIA from {from_address[:10]}..."
    )
    typer.echo(f"🔄 Transactions will be collected and submitted as a group")

    # Connect to ledger for validation
    ledger = Ledger()

    # Reset batch manager to ensure clean state
    batch_manager.reset()

    # List to collect all transactions before submitting
    all_transactions = []
    transaction_details = []

    # First phase: Create all transactions in memory without submitting them
    typer.echo(f"\n📝 Phase 1: Creating transactions in memory...")

    successes = 0
    failures = 0

    for i in range(count):
        try:
            # Get UTXOs - including virtual ones from previous transactions in this batch
            virtual_utxos = batch_manager.get_chained_utxos(from_address)
            db_utxos = db.fetch_unspent_utxos(from_address, include_pending=False)

            # Combine UTXOs for this transaction
            utxos = virtual_utxos + db_utxos

            if not utxos:
                typer.echo(f"❌ No UTXOs available for transaction {i+1}")
                break

            # Create the transaction (but don't submit yet)
            tx = create_transaction(wallet, utxos, to, amount, fee, batch_mode=True)
            
            # Add virtual UTXOs from this transaction to the batch manager
            # This allows the next transaction to use them as inputs
            outputs = []
            for i, output in enumerate(tx.outputs):
                # Create a virtual UTXO with the transaction's txid
                virtual_utxo = UTXO(
                    txid=tx.txid,
                    output_index=i,
                    recipient=output.recipient,
                    amount=output.amount,
                    status="unspent"
                )
                outputs.append(virtual_utxo)
            
            # Add to the batch manager with inputs to mark them as spent
            batch_manager.add_transaction(tx.txid, outputs, tx.inputs)

            # Add to our collection
            all_transactions.append(tx)

            # Store details for reporting
            transaction_details.append(
                {
                    "index": i + 1,
                    "txid": tx.txid,
                    "inputs": len(tx.inputs),
                    "outputs": len(tx.outputs),
                    "amount": amount,
                    "fee": fee,
                }
            )

            typer.echo(
                f"  ✓ Created transaction {i+1}/{count}: {tx.txid[:8]}... with {len(tx.inputs)} inputs"
            )
            successes += 1

        except Exception as e:
            typer.echo(f"❌ Transaction {i+1} creation failed: {str(e)}")
            if "Insufficient funds" in str(e):
                typer.echo("Stopping batch creation due to insufficient funds")
                break
            failures += 1

    # Phase 2: Submit all transactions at once
    if all_transactions:
        typer.echo(
            f"\n📝 Phase 2: Submitting {len(all_transactions)} transactions to the database..."
        )

        for i, tx in enumerate(all_transactions):
            try:
                # Submit the transaction to the database
                db.insert_transaction(tx)
                typer.echo(
                    f"  ✓ Submitted transaction {i+1}/{len(all_transactions)}: {tx.txid[:8]}..."
                )
            except Exception as e:
                typer.echo(f"❌ Failed to submit transaction {tx.txid[:8]}: {str(e)}")

        typer.echo(
            f"\n✅ All {len(all_transactions)} transactions have been submitted as a batch"
        )
        typer.echo(
            f"   They will be processed together in the next block generation cycle"
        )
        block_interval = config.block_interval_seconds
        typer.echo(
            f"   Expect them to be included in a block within {block_interval} seconds"
        )
    else:
        typer.echo(f"\n❌ No transactions were created successfully")

    # Reset batch manager after submission
    batch_manager.reset()

    # Output summary
    typer.echo(f"\n🔍 Batch Test Results:")
    typer.echo(f"📊 Successful transactions: {successes}/{count}")
    typer.echo(f"❌ Failed transactions: {failures}/{count}")

    if successes > 0:
        typer.echo(f"💰 Total sent: {successes * amount} TIA")
        typer.echo(f"💵 Total fees: {successes * fee} TIA")
        typer.echo(f"⏱️ These transactions should be included in a single block")
