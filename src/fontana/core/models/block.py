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


class Block(BaseModel):
    header: BlockHeader
    transactions: List[SignedTransaction]
