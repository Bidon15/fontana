"""
Celestia account client for monitoring accounts and transactions.

This module provides a client for interacting with Celestia accounts,
including retrieving balances and transactions.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from cosmpy.aerial.client import LedgerClient
from cosmpy.aerial.config import NetworkConfig

# Set up logger
logger = logging.getLogger(__name__)

# Regex pattern for extracting recipient from memo
DEPOSIT_MEMO_PATTERN = r"^deposit:(fontana[a-zA-Z0-9]+)$"


@dataclass
class CelestiaTransaction:
    """Information about a Celestia transaction."""

    tx_hash: str
    messages: List[Dict[str, Any]]
    memo: str
    height: int


class CelestiaAccountClient:
    """
    Client for interacting with Celestia accounts.

    This client provides functionality for monitoring accounts,
    retrieving balances, and querying transactions.
    """

    def __init__(self, node_url: str, chain_id: str = "celestia"):
        """
        Initialize the client.

        Args:
            node_url: URL of the Celestia REST API
            chain_id: Chain ID of the Celestia network
        """
        self.chain_id = chain_id

        # Make sure node_url has the required format for cosmpy
        if not node_url.startswith(("http://", "https://")):
            raise ValueError("Node URL must start with http:// or https://")

        # Ensure node_url has the required prefix for cosmpy
        if "rest+" not in node_url:
            if node_url.startswith("http://"):
                node_url = node_url.replace("http://", "rest+http://")
            elif node_url.startswith("https://"):
                node_url = node_url.replace("https://", "rest+https://")

        self.node_url = node_url

        # Configure the network
        self.cfg = NetworkConfig(
            chain_id=chain_id,
            url=node_url,
            fee_minimum_gas_price=0.002,
            fee_denomination="utia",
            staking_denomination="utia",
        )

        # Initialize the ledger client
        self._initialize_client()
        logger.info(f"Connected to Celestia node at {node_url}")

    def _initialize_client(self):
        """Initialize the ledger client. Separated for easier mocking in tests."""
        self.client = LedgerClient(self.cfg)

    def get_account_balance(self, address: str, denom: str = "utia") -> int:
        """
        Get account balance for a specific address.

        Args:
            address: Celestia address to query
            denom: Denomination of the balance (default: utia)

        Returns:
            int: Balance amount in the smallest unit
        """
        try:
            balance = self.client.query_bank_balance(address, denom)
            logger.debug(f"Balance for {address}: {balance} {denom}")
            return balance
        except Exception as e:
            logger.error(f"Error getting balance for {address}: {str(e)}")
            return 0

    def _extract_recipient_from_memo(self, memo: str) -> Optional[str]:
        """
        Extract recipient address from memo.

        Args:
            memo: Transaction memo string

        Returns:
            Optional[str]: Recipient address if found, None otherwise
        """
        if not memo:
            return None

        match = re.match(DEPOSIT_MEMO_PATTERN, memo)
        if match:
            return match.group(1)
        return None

    def get_account_transactions(
        self,
        address: str,
        limit: int = 20,
        offset: int = 0,
        min_height: Optional[int] = None,
    ) -> List[CelestiaTransaction]:
        """
        Get transactions involving a Celestia account.

        Args:
            address: Celestia address to query
            limit: Maximum number of transactions to return
            offset: Offset for pagination
            min_height: Minimum block height to query from

        Returns:
            List[CelestiaTransaction]: List of transactions formatted as CelestiaTransaction objects
        """
        try:
            # Define query parameters
            query_events = [
                f"transfer.recipient='{address}'",
                f"transfer.sender='{address}'",
            ]

            # Query for transactions
            query_path = f"/cosmos/tx/v1beta1/txs?events={','.join(query_events)}&pagination.limit={limit}"
            if min_height is not None:
                query_path += f"&events=tx.height>={min_height}"

            response = self.client.query(query_path)
            txs = response.get("tx_responses", [])

            # Convert to our transaction format
            transactions = []
            for tx_data in txs:
                # Parse the transaction
                tx_hash = tx_data.get("txhash", "")
                height = int(tx_data.get("height", 0))

                # Parse the transaction body
                tx_body = tx_data.get("tx", {}).get("body", {})
                memo = tx_body.get("memo", "")
                messages = tx_body.get("messages", [])

                # Create transaction object
                celestia_tx = CelestiaTransaction(
                    tx_hash=tx_hash, messages=messages, memo=memo, height=height
                )
                transactions.append(celestia_tx)

            return transactions
        except Exception as e:
            logger.error(f"Error getting transactions for {address}: {str(e)}")
            return []

    def get_current_height(self) -> int:
        """
        Get the current block height of the Celestia network.

        Returns:
            int: Current block height
        """
        try:
            status = self.client.query_status()
            height = int(status["sync_info"]["latest_block_height"])
            return height
        except Exception as e:
            logger.error(f"Error getting current height: {str(e)}")
            return 0

    def get_deposits_since_height(
        self,
        vault_address: str,
        from_height: int,
        to_height: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get deposits to a specific vault since a given height.

        Args:
            vault_address: Address of the vault to monitor
            from_height: Block height to start looking from
            to_height: Block height to stop looking at (defaults to current height)
            limit: Maximum number of transactions to process

        Returns:
            List[Dict[str, Any]]: List of deposits formatted as dictionaries
        """
        # Get current height if not specified
        if to_height is None:
            to_height = self.get_current_height()

        logger.info(
            f"Checking for deposits to {vault_address} from height {from_height} to {to_height}"
        )

        # Get transactions for the vault address
        txs = self.get_account_transactions(
            vault_address, limit=limit, min_height=from_height
        )

        # Filter for deposits within the height range
        deposits = []
        for tx in txs:
            # Skip if not in height range
            if tx.height < from_height or (to_height and tx.height > to_height):
                continue

            # Extract recipient from memo
            recipient = self._extract_recipient_from_memo(tx.memo)
            if not recipient:
                continue

            # Parse the transaction to find deposit amount
            for msg in tx.messages:
                # Check if it's a bank send message
                if (
                    msg.get("@type", "") == "/cosmos.bank.v1beta1.MsgSend"
                    and msg.get("to_address") == vault_address
                ):
                    # Parse amount from message
                    amount_list = msg.get("amount", [])
                    for amount_obj in amount_list:
                        if amount_obj.get("denom") == "utia":
                            # Convert amount from utia to TIA
                            amount_utia = int(amount_obj.get("amount", "0"))
                            amount_tia = amount_utia / 1_000_000

                            # Create deposit record
                            deposit = {
                                "l1_tx_hash": tx.tx_hash,
                                "recipient_address": recipient,
                                "amount": amount_tia,
                                "l1_block_height": tx.height,
                                "l1_block_time": 0,  # Can be improved later to get actual timestamp
                            }
                            deposits.append(deposit)

        logger.info(f"Found {len(deposits)} deposits to {vault_address}")
        return deposits
