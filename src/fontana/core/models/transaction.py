import json
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

    def to_sql_row(self) -> dict:
        return {
            "txid": self.txid,
            "sender_address": self.sender_address,
            "inputs_json": json.dumps([ref.model_dump() for ref in self.inputs]),
            "outputs_json": json.dumps([out.to_sql_row() for out in self.outputs]),
            "fee": self.fee,
            "payload_hash": self.payload_hash,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }

    @classmethod
    def from_sql_row(cls, row: dict) -> "SignedTransaction":
        return cls(
            txid=row["txid"],
            sender_address=row["sender_address"],
            inputs=[UTXORef(**ref) for ref in json.loads(row["inputs_json"])],
            outputs=[UTXO.from_sql_row(out) for out in json.loads(row["outputs_json"])],
            fee=row["fee"],
            payload_hash=row["payload_hash"],
            timestamp=row["timestamp"],
            signature=row["signature"],
        )
