import pytest
from fontana.wallet import Wallet
from fontana.core.config import config
import json
import base64

def test_wallet_generate_and_save(tmp_path):
    wallet = Wallet.generate()
    path = tmp_path / "wallet.json"
    wallet.save(str(path))
    
    loaded = Wallet.load(str(path))
    assert loaded.get_address() == wallet.get_address()

def test_wallet_with_config(monkeypatch, tmp_path):
    """Test wallet using config for paths."""
    # Setup temporary path in config
    test_wallet_path = tmp_path / "config_wallet.json"
    monkeypatch.setattr(config, "wallet_path", test_wallet_path)
    
    # Generate and save wallet using config path
    wallet = Wallet.generate()
    wallet.save()  # Should use config path
    
    # Verify the file was created at the config path
    assert test_wallet_path.exists()
    
    # Load wallet using config path
    loaded_wallet = Wallet.load()  # Should use config path
    assert loaded_wallet.get_address() == wallet.get_address()
    
    # Verify the file structure
    with open(test_wallet_path, "r") as f:
        data = json.load(f)
    
    assert "private_key" in data
    # Should be valid base64
    assert base64.b64decode(data["private_key"])