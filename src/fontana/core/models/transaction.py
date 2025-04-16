from pydantic import BaseModel, Field
from typing import List
from fontana.core.models.utxo import UTXO, UTXORef


class SignedTransaction(BaseModel):
    txid: str = Field(..., description="Unique transaction ID (hash of contents)")
    sender_address: str = Field(..., description="Wallet address that signed the TX")
    inputs: List[UTXORef] = Field(..., description="UTXOs being consumed")
    outputs: List[UTXO] = Field(..., description="New UTXOs being created")
    fee: float = Field(..., ge=0, description="Fee in TIA paid to the rollup")
    payload_hash: str = Field(..., description="Hash of the API payload")
    timestamp: int = Field(..., description="Unix timestamp")
    signature: str = Field(..., description="Signature of the TX contents")

    def input_keys(self) -> List[str]:
        return [inp.to_key() for inp in self.inputs]

    def output_keys(self) -> List[str]:
        return [out.key() for out in self.outputs]
