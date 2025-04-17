import json
from pydantic import BaseModel, Field
from fontana.core.models.transaction import SignedTransaction
from fontana.core.models.block import BlockHeader


class ReceiptProof(BaseModel):
    tx: SignedTransaction = Field(..., description="Full transaction used in API call")
    block_header: BlockHeader = Field(..., description="Header of the block including this TX")
    output_index: int = Field(..., ge=0, description="Position of the TX in the block")
    included_at: int = Field(..., description="UTC timestamp of block inclusion")
    provider_url: str = Field(..., description="Endpoint that was called")

    def id(self) -> str:
        return f"{self.tx.txid}:{self.output_index}"

    def summary(self) -> dict:
        return {
            "to": self.tx.outputs[0].recipient,
            "amount": self.tx.outputs[0].amount,
            "block": self.block_header.height,
            "time": self.included_at,
            "endpoint": self.provider_url
        }

    def to_sql_row(self) -> dict:
        return {
            "receipt_id": self.id(),
            "txid": self.tx.txid,
            "block_height": self.block_header.height,
            "timestamp": self.included_at,
            "provider": self.tx.outputs[0].recipient,
            "amount": self.tx.outputs[0].amount,
            "endpoint": self.provider_url,
            "full_json": json.dumps({
                "tx": self.tx.to_sql_row(),
                "block_header": self.block_header.to_sql_row(),
                "output_index": self.output_index,
                "included_at": self.included_at,
                "provider_url": self.provider_url
            })
        }

    @classmethod
    def from_sql_row(cls, row: dict) -> "ReceiptProof":
        raw = json.loads(row["full_json"])
        return cls(
            tx=SignedTransaction.from_sql_row(raw["tx"]),
            block_header=BlockHeader.from_sql_row(raw["block_header"]),
            output_index=raw["output_index"],
            included_at=raw["included_at"],
            provider_url=raw["provider_url"]
        )
