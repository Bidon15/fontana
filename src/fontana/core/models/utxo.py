from pydantic import BaseModel, Field
from typing import Literal


class UTXORef(BaseModel):
    txid: str = Field(..., description="ID of the transaction that created the UTXO")
    index: int = Field(..., description="Index of the output in the transaction")

    def to_key(self) -> str:
        return f"{self.txid}:{self.index}"


class UTXO(BaseModel):
    txid: str = Field(..., description="ID of the transaction that created this output")
    index: int = Field(..., description="Index of the output in the transaction")
    recipient: str = Field(..., description="Address that can spend this output")
    amount: float = Field(..., gt=0, description="Amount in TIA")

    status: Literal["unspent", "spent"] = Field("unspent", description="UTXO status")

    def key(self) -> str:
        return f"{self.txid}:{self.index}"

    def is_spent(self) -> bool:
        return self.status == "spent"
