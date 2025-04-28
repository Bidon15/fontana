"""
Genesis model for initializing the Fontana ledger with a predefined state.
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class GenesisUTXO(BaseModel):
    """An initial UTXO to be created in the genesis block."""
    recipient: str = Field(..., description="Address that can spend this output")
    amount: float = Field(..., gt=0, description="Amount in TIA")


class GenesisState(BaseModel):
    """Defines the initial state of the Fontana ledger."""
    version: str = Field("1.0", description="Genesis format version")
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp()), 
                         description="Genesis timestamp (UTC)")
    utxos: List[GenesisUTXO] = Field(default_factory=list, description="Initial UTXOs")
    initial_state_root: str = Field("0" * 64, description="Initial state root hash")
    description: Optional[str] = Field(None, description="Description of the genesis state")
    
    def to_dict(self) -> dict:
        """Convert the genesis state to a dictionary."""
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "utxos": [utxo.model_dump() for utxo in self.utxos],
            "initial_state_root": self.initial_state_root,
            "description": self.description
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "GenesisState":
        """Create a GenesisState from a dictionary."""
        return cls(
            version=data.get("version", "1.0"),
            timestamp=data.get("timestamp", int(datetime.now().timestamp())),
            utxos=[GenesisUTXO(**utxo) for utxo in data.get("utxos", [])],
            initial_state_root=data.get("initial_state_root", "0" * 64),
            description=data.get("description")
        )
