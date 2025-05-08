# Running the Fontana Rollup

This guide explains how to run the Fontana rollup with Celestia Data Availability integration and monitor transaction processing.

## Prerequisites

- Python 3.10+
- Poetry
- Access to a Celestia node (local or remote)
- SQLite3 command-line tool (for database verification)

## Environment Setup

### Using a .env File (Recommended)

The easiest way to configure Fontana is by creating a `.env` file:

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit the `.env` file with your preferred settings:
   ```bash
   # Use your favorite editor
   nano .env
   ```

3. Load the environment variables when running commands:
   ```bash
   # For bash/zsh
   source .env && poetry run python -m fontana.node

   # Or use a tool like direnv to automatically load
   # the .env file when entering the directory
   ```

### Manual Environment Variables

Alternatively, you can set the following environment variables directly:

```bash
# Celestia DA Configuration
export DA_PROVIDER="celestia"
export CELESTIA_NODE_URL="http://localhost:26658"  # Update with your Celestia node URL
export CELESTIA_AUTH_TOKEN="your_auth_token"       # Only needed if your node requires authentication

# Rollup Configuration
export ROLLUP_DB_PATH="./rollup_data.db"           # Path for SQLite database
export FONTANA_LOG_LEVEL="INFO"                    # Log level (DEBUG, INFO, WARNING, ERROR)
export BLOCK_TIME=15                               # Block generation interval in seconds

# Bridge/Vault Configuration
export L1_VAULT_ADDRESS="celestia1..."             # Your vault address on Celestia
export L1_NODE_URL="http://localhost:26657"        # Celestia RPC endpoint
export L1_POLL_INTERVAL=60                         # How often to check for new deposits (seconds)
export VAULT_WATCHER_DB="./vault_watcher.db"       # Vault watcher database path
```

## Database Initialization

> **Note**: Fontana uses SQLite, a file-based database that doesn't require a separate database server. When we "initialize the database", we're simply creating the .db file with the appropriate tables and initial data.

### Create Data Directory

First, create a directory for the database files:

```bash
mkdir -p data
```

### Initialize Rollup Database

The rollup will automatically initialize its database when you first start the node with the `--init` flag:

```bash
# Make sure ROLLUP_DB_PATH environment variable is set
export ROLLUP_DB_PATH="./data/rollup.db"

# Initialize the database with genesis data
poetry run python -m fontana.node --init --genesis examples/genesis.json
```

This creates the SQLite database file with the required schema and inserts the genesis block and initial UTXOs.

### Initialize Vault Watcher Database

The vault watcher will automatically initialize its database when first started:

```bash
# Make sure VAULT_WATCHER_DB environment variable is set
export VAULT_WATCHER_DB="./data/vault_watcher.db"

# The database will be initialized when you first run the vault watcher
poetry run python scripts/vault_watcher.py
```

### Access to Genesis Funds

To create transactions, you'll need access to a wallet with funds. The provided script creates a deterministic wallet and a custom genesis file that funds this wallet:

```bash
# Create a genesis wallet and a custom genesis file
poetry run python scripts/create_genesis_wallet.py --update-genesis --force
```

This will:
1. Create a wallet at `~/.fontana/genesis.json` with a deterministic private key
2. Create a custom genesis file at `examples/custom_genesis.json` with this wallet funded

Now you can initialize your node with this custom genesis file:

```bash
# Initialize the node with custom genesis
poetry run python -m fontana.node --init --genesis examples/custom_genesis.json

# Start the node
poetry run python -m fontana.node --rpc-port 8545
```

Verify that your wallet has funds:

```bash
# Check wallet balance
poetry run python -m fontana.cli wallet balance --name genesis --rpc-url http://localhost:8545
```

This wallet can now be used in the test scripts to fund test transactions.

## Starting the Rollup Node

Start the node with RPC server enabled:

```bash
# First, make sure your database is initialized
poetry run python -m fontana.node --init --genesis examples/genesis.json

# Then start the node
poetry run python -m fontana.node --rpc-port 8545
```

The node will start generating blocks according to the configured block time, processing transactions, and submitting blocks to Celestia DA.

## Starting the Vault Watcher

In a separate terminal, start the vault watcher to monitor for deposits from Celestia:

```bash
poetry run python scripts/vault_watcher.py
```

The vault watcher will poll Celestia for new deposits to the configured vault address and process them through the bridge.

## Creating and Using Wallets

### Generate new wallets

```bash
# Create a sender wallet
poetry run python -m fontana.cli wallet new --name sender

# Create a receiver wallet
poetry run python -m fontana.cli wallet new --name receiver
```

### Check wallet balances

```bash
poetry run python -m fontana.cli wallet balance --name sender
poetry run python -m fontana.cli wallet balance --name receiver
```

### Send transactions

```bash
# Get the receiver's address
RECEIVER_ADDRESS=$(poetry run python -m fontana.cli wallet address --name receiver)

# Send 10 tokens from sender to receiver
poetry run python -m fontana.cli tx send --from sender --to $RECEIVER_ADDRESS --amount 10 --rpc-url http://localhost:8545
```

## Monitoring the Rollup

### View chain information

```bash
poetry run python -m fontana.cli chain info --rpc-url http://localhost:8545
```

### List blocks

```bash
poetry run python -m fontana.cli chain list-blocks --rpc-url http://localhost:8545
```

### View block details

```bash
poetry run python -m fontana.cli chain get-block --height 1 --rpc-url http://localhost:8545
```

### Check Celestia DA status

To verify that block data has been posted to Celestia, you can use the Celestia CLI:

```bash
# If you have celestia-node installed
celestia namespace get <namespace-id>

# Get the namespace ID from your logs or configuration
```

The namespace ID is deterministically generated based on the block height and chain ID, but you can also specify a custom namespace ID in your configuration.

## Database Verification

The rollup uses SQLite databases. You can directly examine them to verify state:

```bash
# View rollup state database
sqlite3 $ROLLUP_DB_PATH <<EOF
.headers on
.mode column
SELECT * FROM utxos;
SELECT * FROM blocks ORDER BY height DESC LIMIT 5;
SELECT * FROM transactions ORDER BY id DESC LIMIT 10;
EOF

# View vault watcher database
sqlite3 $VAULT_WATCHER_DB <<EOF
.headers on
.mode column
SELECT * FROM vault_deposits;
SELECT * FROM system_vars;
EOF
```

## Running Automated Tests

You can use the included test script to automatically create wallets, send transactions, and verify the system state:

```bash
# First create the genesis wallet to fund test transactions
poetry run python scripts/create_genesis_wallet.py

# Start the node in a separate terminal first
poetry run python -m fontana.node --rpc-port 8545

# Run the test script
poetry run python scripts/test_transactions.py --rpc-url http://localhost:8545 --genesis-wallet genesis
```

The test script will:
1. Create multiple test wallets
2. Fund them from the genesis wallet
3. Perform transactions between the test wallets
4. Verify transaction success and database state

## Troubleshooting

- **Node won't start**: Check that environment variables are properly set and the database path is accessible
- **Celestia posting failures**: Verify your Celestia node is running and the URL/auth token are correct
- **Transaction failures**: Check log output for error messages and ensure wallets have sufficient balance
- **Database errors**: Make sure the database files are writable and not corrupted

### Common Issues

1. **"Error: failed to connect to Celestia node"**
   - Ensure the Celestia node is running
   - Check the CELESTIA_NODE_URL value is correct
   - Verify network connectivity to the Celestia node

2. **"Error: database is locked"**
   - Another process might be using the database
   - Check for zombie processes and kill them if necessary

3. **"Error: invalid namespace ID"**
   - The namespace ID must be a 16-character hex string (8 bytes)
   - Use a valid namespace ID or let the system generate one for you

## Advanced Configuration

For more advanced configuration options, refer to the source code or create a configuration file with custom settings.
