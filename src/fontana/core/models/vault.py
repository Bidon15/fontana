import json
from pydantic import BaseModel, Field
from typing import List
from fontana.core.models.utxo import UTXO

class VaultDeposit(BaseModel):
    depositor_address: str = Field(..., description="Celestia address that sent the deposit (may be a CEX)")
    rollup_wallet_address: str = Field(..., description="Fontana rollup address to credit")
    vault_address: str = Field(..., description="Celestia vault multisig that received the deposit")
    tx_hash: str = Field(..., description="Celestia L1 TX hash of the deposit")
    amount: float = Field(..., gt=0, description="Amount of TIA deposited")
    timestamp: int = Field(..., description="When the deposit was seen")
    height: int = Field(..., ge=0, description="Celestia block height of inclusion")
    processed: bool = Field(False, description="Whether a UTXO was minted for this deposit")

    def id(self) -> str:
        return f"{self.tx_hash}:{self.rollup_wallet_address}"
    
    def to_sql_row(self) -> dict:
        return {
            "depositor_address": self.depositor_address,
            "rollup_wallet_address": self.rollup_wallet_address,
            "vault_address": self.vault_address,
            "tx_hash": self.tx_hash,
            "amount": self.amount,
            "timestamp": self.timestamp,
            "height": self.height,
            "processed": self.processed
        }

    @classmethod
    def from_sql_row(cls, row: dict) -> "VaultDeposit":
        return cls(
            depositor_address=row["depositor_address"],
            rollup_wallet_address=row["rollup_wallet_address"],
            vault_address=row["vault_address"],
            tx_hash=row["tx_hash"],
            amount=row["amount"],
            timestamp=row["timestamp"],
            height=row["height"],
            processed=row["processed"]
        )


class VaultWithdrawal(BaseModel):
    recipient_rollup_address: str = Field(..., description="User's rollup address requesting withdrawal")
    recipient_celestia_address: str = Field(..., description="Where TIA was sent back on Celestia")
    vault_address: str = Field(..., description="Which multisig sent the withdrawal")
    amount: float = Field(..., gt=0, description="Amount withdrawn (in TIA)")
    timestamp: int = Field(..., description="UTC timestamp of the manual payout")
    related_utxos: List[UTXO] = Field(..., description="List of UTXOs burned for withdrawal")
    tx_hash: str = Field(..., description="Celestia L1 TX hash of the withdrawal")
    processed_by: str = Field(..., description="Operator name or wallet tag")

    def id(self) -> str:
        return f"{self.tx_hash}:{self.recipient_rollup_address}"
    
    def to_sql_row(self) -> dict:
        return {
            "recipient_rollup_address": self.recipient_rollup_address,
            "recipient_celestia_address": self.recipient_celestia_address,
            "vault_address": self.vault_address,
            "amount": self.amount,
            "timestamp": self.timestamp,
            "related_utxos_json": json.dumps([u.model_dump() for u in self.related_utxos]),
            "tx_hash": self.tx_hash,
            "processed_by": self.processed_by
        }

    @classmethod
    def from_sql_row(cls, row: dict) -> "VaultWithdrawal":
        return cls(
            recipient_rollup_address=row["recipient_rollup_address"],
            recipient_celestia_address=row["recipient_celestia_address"],
            vault_address=row["vault_address"],
            amount=row["amount"],
            timestamp=row["timestamp"],
            related_utxos=[UTXO(**u) for u in json.loads(row["related_utxos_json"])],
            tx_hash=row["tx_hash"],
            processed_by=row["processed_by"]
        )
