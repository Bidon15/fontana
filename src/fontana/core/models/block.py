import json
from pydantic import BaseModel, Field
from typing import List
from fontana.core.models.transaction import SignedTransaction


class BlockHeader(BaseModel):
    height: int = Field(..., ge=0, description="Rollup block height")
    prev_hash: str = Field(..., description="Hash of previous block")
    state_root: str = Field(..., description="Root hash of UTXO set after this block")
    timestamp: int = Field(..., description="Block timestamp (UTC)")
    tx_count: int = Field(..., ge=0, description="Number of TXs in block")
    blob_ref: str = Field(..., description="Reference to the Celestia blob (optional)")
    fee_schedule_id: str = Field(..., description="Versioned ID for provider fee policy")

    def id(self) -> str:
        return f"{self.height}:{self.state_root}"

    def to_sql_row(self) -> dict:
        return {
            "height": self.height,
            "prev_hash": self.prev_hash,
            "state_root": self.state_root,
            "timestamp": self.timestamp,
            "tx_count": self.tx_count,
            "blob_ref": self.blob_ref,
            "fee_schedule_id": self.fee_schedule_id
        }

    @classmethod
    def from_sql_row(cls, row: dict) -> "BlockHeader":
        return cls(
            height=row["height"],
            prev_hash=row["prev_hash"],
            state_root=row["state_root"],
            timestamp=row["timestamp"],
            tx_count=row["tx_count"],
            blob_ref=row["blob_ref"],
            fee_schedule_id=row["fee_schedule_id"]
        )


class Block(BaseModel):
    header: BlockHeader
    transactions: List[SignedTransaction]

    def to_sql_row(self) -> dict:
        return {
            "height": self.header.height,
            "header_json": json.dumps(self.header.to_sql_row()),
            "txs_json": json.dumps([tx.to_sql_row() for tx in self.transactions]),
            "committed": False,
            "blob_ref": None
        }

    @classmethod
    def from_sql_row(cls, row: dict) -> "Block":
        return cls(
            header=BlockHeader.from_sql_row(json.loads(row["header_json"])),
            transactions=[SignedTransaction.from_sql_row(tx) for tx in json.loads(row["txs_json"])]
        )
