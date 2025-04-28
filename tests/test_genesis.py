import json
import pytest
from pathlib import Path
from datetime import datetime
from fontana.core.models.genesis import GenesisState, GenesisUTXO


def test_genesis_utxo_validation():
    """Test UTXO validation for genesis state."""
    # Valid UTXO
    utxo = GenesisUTXO(recipient="abc123", amount=100.0)
    assert utxo.recipient == "abc123"
    assert utxo.amount == 100.0
    
    # Invalid amount (non-positive)
    with pytest.raises(ValueError):
        GenesisUTXO(recipient="abc123", amount=0)
    
    with pytest.raises(ValueError):
        GenesisUTXO(recipient="abc123", amount=-10)


def test_genesis_state_creation():
    """Test creating a genesis state."""
    # Create with defaults
    state = GenesisState()
    assert state.version == "1.0"
    assert isinstance(state.timestamp, int)
    assert len(state.utxos) == 0
    assert state.initial_state_root == "0" * 64
    
    # Create with custom values
    utxos = [
        GenesisUTXO(recipient="wallet1", amount=1000.0),
        GenesisUTXO(recipient="wallet2", amount=500.0)
    ]
    timestamp = int(datetime.now().timestamp())
    state = GenesisState(
        version="1.1",
        timestamp=timestamp,
        utxos=utxos,
        initial_state_root="abc" + "0" * 61,
        description="Test genesis state"
    )
    
    assert state.version == "1.1"
    assert state.timestamp == timestamp
    assert len(state.utxos) == 2
    assert state.utxos[0].recipient == "wallet1"
    assert state.utxos[1].amount == 500.0
    assert state.initial_state_root == "abc" + "0" * 61
    assert state.description == "Test genesis state"


def test_genesis_serialization():
    """Test serializing and deserializing genesis state."""
    # Create a state
    utxos = [
        GenesisUTXO(recipient="wallet1", amount=1000.0),
        GenesisUTXO(recipient="wallet2", amount=500.0)
    ]
    original = GenesisState(
        utxos=utxos,
        description="Test genesis"
    )
    
    # Convert to dict and back
    data = original.to_dict()
    loaded = GenesisState.from_dict(data)
    
    # Check values match
    assert loaded.version == original.version
    assert loaded.timestamp == original.timestamp
    assert len(loaded.utxos) == len(original.utxos)
    assert loaded.utxos[0].recipient == original.utxos[0].recipient
    assert loaded.utxos[1].amount == original.utxos[1].amount
    assert loaded.initial_state_root == original.initial_state_root
    assert loaded.description == original.description
    
    # Test with JSON roundtrip
    json_str = json.dumps(data)
    loaded_json = json.loads(json_str)
    loaded_from_json = GenesisState.from_dict(loaded_json)
    
    assert loaded_from_json.version == original.version
    assert len(loaded_from_json.utxos) == len(original.utxos)


def test_example_genesis_file(tmp_path):
    """Test loading the example genesis file."""
    # Create a temporary genesis file
    genesis_file = tmp_path / "test_genesis.json"
    example_data = {
        "version": "1.0",
        "timestamp": 1714489547,
        "description": "Fontana testnet initial state",
        "initial_state_root": "0000000000000000000000000000000000000000000000000000000000000000",
        "utxos": [
            {
                "recipient": "wallet1",
                "amount": 1000.0
            },
            {
                "recipient": "wallet2",
                "amount": 500.0
            }
        ]
    }
    
    with open(genesis_file, "w") as f:
        json.dump(example_data, f)
    
    # Load the file
    with open(genesis_file, "r") as f:
        data = json.load(f)
    
    state = GenesisState.from_dict(data)
    
    # Check values
    assert state.version == "1.0"
    assert state.timestamp == 1714489547
    assert state.description == "Fontana testnet initial state"
    assert len(state.utxos) == 2
    assert state.utxos[0].amount == 1000.0
    assert state.utxos[1].recipient == "wallet2"
