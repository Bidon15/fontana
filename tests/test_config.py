import pytest
from pathlib import Path
from fontana.core.config import FontanaConfig, load_config_from_env


def test_config_defaults():
    """Test that the configuration has expected defaults."""
    config = FontanaConfig()
    
    # Check database defaults
    assert config.db_path == Path.home() / ".fontana" / "ledger.db"
    
    # Check wallet defaults
    assert config.wallet_path == Path.home() / ".fontana" / "wallet.json"
    
    # Check block generation defaults
    assert config.block_interval_seconds == 6
    assert config.max_tx_per_block == 100
    assert config.fee_schedule_id == "v1"


def test_config_override(monkeypatch):
    """Test that environment variables override defaults."""
    # Set environment variables
    monkeypatch.setenv("FONTANA_DB_PATH", "/tmp/test_ledger.db")
    monkeypatch.setenv("FONTANA_WALLET_PATH", "/tmp/test_wallet.json")
    monkeypatch.setenv("FONTANA_BLOCK_INTERVAL_SECONDS", "10")
    monkeypatch.setenv("FONTANA_CELESTIA_NODE_URL", "http://localhost:26658")
    
    # Load config from environment
    config = load_config_from_env()
    
    # Check that values were overridden
    assert config.db_path == Path("/tmp/test_ledger.db")
    assert config.wallet_path == Path("/tmp/test_wallet.json")
    assert config.block_interval_seconds == 10
    assert config.celestia_node_url == "http://localhost:26658"


def test_config_validation():
    """Test that configuration values are validated."""
    # Test with invalid value
    with pytest.raises(ValueError):
        FontanaConfig(block_interval_seconds=-1)
    
    # Test with valid value
    config = FontanaConfig(block_interval_seconds=1)
    assert config.block_interval_seconds == 1
