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
    
    # Block Generator Configuration
    block_interval_seconds: int = Field(
        default=5,  # Changed from 60 to 5 seconds for faster blocks
        description="Time in seconds between block generation attempts"
    )
    max_block_transactions: int = Field(
        default=100,
        description="Maximum number of transactions to include in a block"
    )
    
    # Fee Configuration
    minimum_transaction_fee: float = Field(
        default=0.01,
        description="Minimum fee required for all transactions"
    )
    fee_schedule_id: str = Field(
        default="default",
        description="ID of the fee schedule to use for transactions"
    )
    
    @field_validator('block_interval_seconds')
    def validate_block_interval(cls, value):
        """Validate block interval is positive."""
        if value <= 0:
            raise ValueError("Block interval must be greater than 0")
        return value
    
    @field_validator('minimum_transaction_fee')
    def validate_minimum_fee(cls, value):
        """Validate minimum transaction fee is non-negative."""
        if value < 0:
            raise ValueError("Minimum transaction fee cannot be negative")
        return value
    
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
        "FONTANA_MAX_BLOCK_TRANSACTIONS": "max_block_transactions",
        "FONTANA_MINIMUM_TRANSACTION_FEE": "minimum_transaction_fee",
        "FONTANA_FEE_SCHEDULE_ID": "fee_schedule_id"
    }
    
    # Get values from environment
    for env_var, field_name in env_mappings.items():
        if env_var in os.environ:
            value = os.environ[env_var]
            
            # Handle type conversions
            if field_name in ["db_path", "wallet_path", "genesis_file"]:
                value = Path(value)
            elif field_name in ["block_interval_seconds", "max_block_transactions"]:
                value = int(value)
            elif field_name == "minimum_transaction_fee":
                value = float(value)
                
            env_settings[field_name] = value
    
    # Create config with environment settings
    return FontanaConfig(**env_settings)
