from pydantic import BaseModel, Field
from typing import Literal


class UTXORef(BaseModel):
    txid: str = Field(..., description="ID of the transaction that created the UTXO")
    output_index: int = Field(
        ..., description="output_index of the output in the transaction"
    )

    def to_key(self) -> str:
        return f"{self.txid}:{self.output_index}"


class UTXO(BaseModel):
    txid: str = Field(..., description="ID of the transaction that created this output")
    output_index: int = Field(
        ..., description="output_index of the output in the transaction"
    )
    recipient: str = Field(..., description="Address that can spend this output")
    amount: float = Field(..., gt=0, description="Amount in TIA")

    status: Literal["unspent", "spent"] = Field("unspent", description="UTXO status")

    def key(self) -> str:
        return f"{self.txid}:{self.output_index}"

    def is_spent(self) -> bool:
        return self.status == "spent"

    def to_sql_row(self) -> dict:
        return {
            "txid": self.txid,
            "output_index": self.output_index,
            "recipient": self.recipient,
            "amount": self.amount,
            "status": self.status,
        }

    @classmethod
    def from_sql_row(cls, row: dict) -> "UTXO":
        return cls(
            txid=row["txid"],
            output_index=row["output_index"],
            recipient=row["recipient"],
            amount=row["amount"],
            status=row["status"],
        )
