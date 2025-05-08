# 🛠 Fontana

**Fontana** is a simple, UTXO-based payment system designed for Python/Django developers.  
It enables devs to charge and pay per API call using TIA — no keys, no Stripe, no OAuth.

Just deploy, connect, and make money flow like a fontana.

---

## 📁 Project Structure

```
src/fontana/                  # Python package (created via `poetry new fontana`)
├── __init__.py
├── bridge/                   # L1 bridge integration (e.g. Celestia bridge)
│   └── celestia/             # Celestia-specific bridge implementation

├── core/                     # Core rollup components
│   ├── block_generator/      # Block generation and transaction processing
│   │   ├── generator.py      # BlockGenerator class for creating blocks
│   │   └── processor.py      # TransactionProcessor for managing tx queue
│   ├── crypto/               # Cryptographic utilities
│   ├── da/                   # Data Availability layer integration
│   │   ├── client.py         # CelestiaClient for Celestia DA
│   │   └── pylestia/         # Pylestia Rust extension for Celestia
│   ├── db/                   # Database access and management
│   ├── ledger/               # UTXO ledger implementation
│   │   └── ledger.py         # Core Ledger class for tx validation/application
│   ├── models/               # Data models and schemas
│   │   ├── block.py          # Block model
│   │   ├── genesis.py        # Genesis state model
│   │   ├── transaction.py    # Transaction models
│   │   └── utxo.py           # UTXO model
│   ├── notifications/        # Notification system for events
│   └── state_merkle/         # Sparse Merkle Tree for state commitments

├── wallet/                   # SSH-style wallet and key management
├── sdk/                      # Python SDK for API consumers
└── cli/                      # Command-line interface tools

scripts/                      # Utility scripts for node operation
├── initialize_ledger.py      # Initialize ledger with genesis state
├── run_node.py               # Run a complete Fontana rollup node
└── debug_celestia_connection.py # Diagnostic tool for Celestia connections

tests/                        # Unit and integration tests
├── test_block_generator.py   # Block generator tests
├── test_celestia_client.py   # Celestia client tests
├── test_ledger.py            # Ledger tests
└── test_transaction_processor.py # Transaction processor tests

examples/                     # Example applications and configurations
└── custom_genesis.json       # Sample genesis state
```

---

## 🏁 Quickstart

```bash
# Install dependencies
poetry install

# Build Pylestia Rust extension (required for Celestia DA integration)
cd src/fontana/core/da/pylestia
maturin develop --release

# Enter virtual environment
poetry shell
```

```bash
# CLI usage (to be implemented)
fontana init                # Create SSH-style wallet
fontana topup 10            # Load TIA from vault
fontana-call \
  --to https://api.example.com/summary \
  --input input.json \
  --max-price 0.01
```

## 🚀 Running a Fontana Rollup Node

Fontana works as a full rollup node that connects to Celestia for data availability. Follow these steps to run your own node:

### 1. Configure Environment Variables

Copy the provided example environment file:

```bash
cp .env.example .env
```

Edit the `.env` file to set up your configuration. At minimum, you'll need:

```
# Database Configuration
ROLLUP_DB_PATH="data/rollup.db"  # Where to store the UTXO data

# Celestia Data Availability Configuration
CELESTIA_NODE_URL="http://localhost:26658"  # Your Celestia Light Node URL
CELESTIA_AUTH_TOKEN="your-auth-token"       # Auth token from your Celestia node
CELESTIA_NAMESPACE_ID="0123456789abcdef"    # 16-character hex namespace ID (MUST be a valid 8-byte/16-char hex)
```

### 2. Initialize the Ledger

Before running the node, you need to initialize the ledger with genesis state:

```bash
python scripts/initialize_ledger.py --genesis examples/custom_genesis.json --force
```

Options:
- `--genesis PATH`: Path to the genesis file (default: examples/custom_genesis.json)
- `--force`: Force reinitialization even if the database already exists
- `--db-path PATH`: Custom database path (default: ~/.fontana/ledger.db or value from ROLLUP_DB_PATH)

### 3. Start the Rollup Node

Run the node with the following command:

```bash
python scripts/run_node.py --rpc-port 8545
```

Options:
- `--rpc-port PORT`: JSON-RPC port for the API (default: 8545)
- `--force-init`: Force ledger initialization on startup
- `--genesis PATH`: Path to genesis file if initialization is needed

The node will:
1. Load environment variables from `.env`
2. Connect to the Celestia node for data availability
3. Start processing transactions and generating blocks
4. Submit blocks to Celestia for DA
5. Expose an API endpoint for submitting transactions

## 🌌 Celestia Integration

Fontana uses Celestia as its data availability layer through the pylestia Rust extension. Here are important details about this integration:

### Namespace Requirements

- Namespace IDs must be valid 8-byte hex values (16 characters) that can be properly normalized by the Rust extension
- The system generates deterministic namespace IDs for blocks using a hash function
- Hex strings are converted to bytes properly before being passed to API calls

### Key Integration Points

- **Posting blocks**: The `CelestiaClient.post_block` method submits block data to Celestia
- **Confirmation checks**: The `CelestiaClient.check_confirmation` method verifies block inclusion in Celestia
- **Namespaces**: The system handles namespace generation and conversion via `_namespace_id_bytes` and `_get_namespace_for_block` methods

### Required Environment Variables

For the Celestia integration to work properly, these environment variables must be set:

```
CELESTIA_NODE_URL      # URL of the Celestia node (usually a local light node)
CELESTIA_AUTH_TOKEN    # Authentication token for the Celestia node
CELESTIA_NAMESPACE_ID  # Valid 16-character hex namespace ID
ROLLUP_DB_PATH         # Path to the rollup database
```

---

## 🎯 Core Goals

- One-line monetization for Django APIs: `@charge(tia=...)`
- SSH-style keys instead of seed phrases
- Pay-per-request using real UTXOs (no auth tokens)
- API composability by default
- Celestia used as the data availability & recovery layer

---

## 🤝 Team

Built in Berlin and Odesa.  
Inspired by Odesa's Fontana district — where things flow with chill vibes.
