from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class FontanaConfig(BaseModel):
    """Base configuration for Fontana components.
    
    This model loads configuration from environment variables and defaults.
    """
    # Database Configuration
    db_path: Path = Field(
        default=Path.home() / ".fontana" / "ledger.db",
        description="Path to the SQLite database file"
    )
    
    # Genesis Configuration
    genesis_file: Optional[Path] = Field(
        default=None,
        description="Path to the genesis file for initial state"
    )
    
    # Wallet Configuration
    wallet_path: Path = Field(
        default=Path.home() / ".fontana" / "wallet.json",
        description="Path to the wallet file"
    )
    
    # Celestia Data Availability Configuration
    celestia_node_url: Optional[str] = Field(
        default=None,
        description="URL of the Celestia node"
    )
    celestia_auth_token: Optional[str] = Field(
        default=None,
        description="Auth token for Celestia node"
    )
    celestia_namespace: Optional[str] = Field(
        default=None,
        description="Namespace for Celestia blobs"
    )
    
    # L1 Bridge Configuration
    l1_node_url: Optional[str] = Field(
        default=None,
        description="URL of the L1 node"
    )
    l1_vault_address: Optional[str] = Field(
        default=None,
        description="Address of the vault on L1"
    )
    
    # Block Generation Configuration
    block_interval_seconds: int = Field(
        default=6,
        description="Target interval between blocks in seconds",
        gt=0
    )
    max_tx_per_block: int = Field(
        default=100,
        description="Maximum number of transactions per block"
    )
    fee_schedule_id: str = Field(
        default="v1",
        description="Version identifier for fee policy"
    )
    
    @field_validator('block_interval_seconds')
    def block_interval_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('block_interval_seconds must be positive')
        return v
    
    model_config = {
        "env_prefix": "FONTANA_",
        "arbitrary_types_allowed": True,
        "validate_assignment": True,
    }


# Global config instance with default values
config = FontanaConfig()

def load_config_from_env() -> FontanaConfig:
    """Load configuration from environment variables.
    
    Returns:
        FontanaConfig: Configuration instance with values from environment
    """
    import os
    
    # Create a dict of settings from environment variables
    env_settings = {}
    
    # Map environment variables to config fields
    env_mappings = {
        "FONTANA_DB_PATH": "db_path",
        "FONTANA_WALLET_PATH": "wallet_path",
        "FONTANA_GENESIS_FILE": "genesis_file",
        "FONTANA_CELESTIA_NODE_URL": "celestia_node_url",
        "FONTANA_CELESTIA_AUTH_TOKEN": "celestia_auth_token", 
        "FONTANA_CELESTIA_NAMESPACE": "celestia_namespace",
        "FONTANA_L1_NODE_URL": "l1_node_url",
        "FONTANA_L1_VAULT_ADDRESS": "l1_vault_address",
        "FONTANA_BLOCK_INTERVAL_SECONDS": "block_interval_seconds",
        "FONTANA_MAX_TX_PER_BLOCK": "max_tx_per_block",
        "FONTANA_FEE_SCHEDULE_ID": "fee_schedule_id"
    }
    
    # Get values from environment
    for env_var, field_name in env_mappings.items():
        if env_var in os.environ:
            value = os.environ[env_var]
            
            # Handle type conversions
            if field_name in ["db_path", "wallet_path", "genesis_file"]:
                value = Path(value)
            elif field_name in ["block_interval_seconds", "max_tx_per_block"]:
                value = int(value)
                
            env_settings[field_name] = value
    
    # Create config with environment settings
    return FontanaConfig(**env_settings)
