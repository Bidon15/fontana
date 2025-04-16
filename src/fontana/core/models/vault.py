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
