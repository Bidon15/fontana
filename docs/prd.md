# 🛠 Fontana - Product Requirements Document (PRD)

**Version:** 1.3 (Draft)
**Date:** [Current Date]

**Fontana** is a simple, UTXO-based payment system library designed for Python developers. It provides the core components to build applications enabling pay-per-call billing using TIA on a dedicated rollup. Data availability is secured via Celestia. Asset bridging relies on interfacing with an external component (planned: Rust/Hyperlane). State transitions are cryptographically committed using state roots and verifiable via Merkle proofs.

---

## 1. Goals

-   Provide Core Rollup Logic: Offer building blocks (ledger with integrated validation, state root calculation, and Merkle proof generation capability), sequencing logic for a UTXO-based payment rollup.
-   Simplified Wallet Management: Include utilities for SSH-style key management and transaction signing.
-   Celestia Data Availability: Integrate with Celestia via `pylestia` for posting block data (including empty blocks) frequently.
-   API Monetization Pattern: Enable easy integration into frameworks like Django for pay-per-call APIs via provided plugin components.
-   **API Composability:** Design the system to allow Fontana-powered providers to act as consumers of other Fontana-powered APIs.
-   Decoupled Bridging: Define clear interfaces (`src/fontana/bridge`) for interacting with an external L1 bridge mechanism, supported by state roots and Merkle proofs for secure verification.
-   Maintainable Structure: Keep core library logic separate (`src/fontana/`) from operational scripts/daemons (`scripts/`).
-   Verifiable State: Ensure rollup state transitions and individual state elements (like UTXOs) are verifiable through state roots and Merkle proofs.
-   **Standardized Configuration:** Utilize a unified configuration mechanism (e.g., Pydantic BaseSettings) for loading parameters.

---

## 2. Key Features & Components

### 2.1. Fontana Core Library (`src/fontana/`)

-   **Configuration (`core/config.py`):**
    -   Pydantic `BaseSettings` model to load configuration from environment variables (`.env`) and potentially other sources. Provides typed access to settings like DB path, Celestia Node URL/Token/Namespace, genesis info, intervals, etc.
-   **Core Models (`core/models/`):**
    -   Pydantic models (UTXO, Transaction, BlockHeader including `state_root`, Block, ReceiptProof, VaultDeposit/Withdrawal events).
-   **Database Interaction (`core/db/`):**
    -   SQLite schema definition and interaction functions.
-   **Ledger Engine (`core/ledger/`):**
    -   Integrates transaction validation (signature, funds, inputs).
    -   Calculates state root (e.g., via Merkle tree) after state changes.
    -   Provides internal capability to generate Merkle proofs for UTXOs.
    *   `apply_transaction(tx)`: Validates then atomically updates DB and state root structure.
    *   `process_deposit_event(details)`: Processes L1 deposit signals.
    *   `process_withdrawal_event(details)`: Processes L1 withdrawal confirmation signals.
    *   Provides state/proof queries (`get_balance`, `get_current_state_root`, potentially `get_utxo_merkle_proof`).
-   **Sequencing Logic (`core/sequencing/`):**
    *   `BlockSequencer` logic: Queries ledger, batches TXs (or determines empty block), constructs `Block` (including state root from ledger), provides block for local commit. Logic aims for frequent block production (e.g., ~6 seconds if feasible).
-   **Data Availability Interface (`core/da/`):**
    *   `CelestiaDA` abstraction using `pylestia`.
    *   `post_block(block)`: Posts Fontana block data (transactions or empty block marker) to Celestia. Returns `blob_ref`. Handles failures with retries/logging (no automatic local rollback).
    *   `fetch_block_data(blob_ref)`: Retrieves data for recovery.
-   **Wallet (`wallet/`):**
    -   Key management and signing utilities.
-   **Bridge Interface (`bridge/`):**
    -   `handler.py` defining functions (`handle_deposit_received`, `handle_withdrawal_confirmed`) called by the external bridge.

### 2.2. Operational Scripts/Daemons (`scripts/`)

-   **Genesis Utility (`scripts/create_genesis.py`):**
    *   Script to initialize the database (DB schema, Block 0 record with genesis state root) based on a configuration file defining the initial state (e.g., pre-mined UTXOs).
-   **Block Generator (`scripts/block_gen.py`):**
    *   Daemon driving the `core.sequencing` logic. Aims to produce blocks frequently (e.g., target ~6s), including **empty blocks** if no transactions are pending, to maintain consistent DA posting rhythm. Commits block locally (`committed=0`).
-   **Blob Poster (`scripts/blob_poster.py`):**
    *   Daemon polling for uncommitted blocks (`committed=0`, including empty ones).
    *   Calls `core.da.post_block()` for each. Updates DB (`committed=1`, `blob_ref`) on success. Implements retries and alerting on persistent failures.
-   **Vault Watcher (`scripts/vault_watcher.py`):**
    *   Daemon monitoring L1 bridge/vault. Calls `bridge.handler.handle_deposit_received` on detection.
-   **Withdrawal Processor (`scripts/withdrawal_processor.py`):**
    *   Daemon/script coordinating L1 withdrawal. Fetches proofs from `ledger`, interacts with external bridge/L1 wallet, calls `bridge.handler.handle_withdrawal_confirmed` on L1 success.
-   **Recovery Tool (`scripts/recover_ledger.py`):**
    *   Utility script to rebuild ledger state from DA, verifying state roots.

### 2.3. SDK (`src/fontana/sdk/`) (Future)

-   Python library for API *consumers*.
-   Includes UTXO management (caching, locking, JIT splitting).
-   Constructs/signs transactions. Sends API requests.
-   Handles **provisional receipts**. Verifies finality later if needed (checking DA status via provider or DA directly).
-   **Provider-Side Usage:** Needs consideration for how a provider uses the SDK (or similar logic) to call other APIs, managing its own wallet/UTXOs distinct from its provider role.

### 2.4. Django Plugin (`src/fontana/django_plugin/`) (Future)

-   `@charge` decorator calls `ledger.apply_transaction`.
-   Generates **provisional receipts** referencing the locally committed block, allowing immediate response to the consumer.

### 2.5. Command-Line Interface (`src/fontana/cli/`)

-   User tools (`init`, `show`, `balance`, `call`, `withdraw`). Uses unified config.
-   Test trigger commands (`trigger-deposit`, `trigger-withdrawal-confirm`).

### 2.6. Rust Bridge Component (`rust/` - Future)

-   Planned location for Rust/Hyperlane logic. Requires Merkle proofs.

### 2.7. Monitoring

-   Integration points for Prometheus metrics within key components (ledger apply rate, block interval, DA post time, queue lengths, etc.) for essential observability.

---

## 3. Architecture Overview

*(Flow mostly unchanged, but receipts are provisional, empty blocks are generated/posted, and provider-composability is a consideration)*

---

## 4. Non-Functional Requirements

-   Modularity, Configurability (via `core.config`), Bridging Interface, Testability.
-   State Integrity & Verifiability (Roots & Proofs).
-   **Liveness:** Rollup progresses via empty blocks even with no user activity.
-   **DA Frequency:** Blocks (empty or not) are posted frequently to Celestia.
-   **Error Handling:** Persistent DA posting failures require alerting/manual intervention, but do not cause automatic local state rollback.
-   **No DoS Limits (Initial):** The system will not implement transaction/block size limits initially. Rate limiting may be added later outside the core protocol.
-   **Finality Assumption:** Relies on Celestia's Tendermint finality (single slot); no complex handling for short L1 reorgs needed for DA references.
-   **Monitoring:** Essential metrics exposed for Prometheus.
-   **Upgrades:** Handled via hard forks (TBD).

---

## 5. Out of Scope (Initial Versions)

-   Full SDK advanced features (locking, splitting, proof *verification*).
-   Full Django plugin receipt finality checking.
-   Full Rust bridge implementation/integration.
-   *Exposing* Merkle proof generation via a public API.
-   Automated withdrawal processor L1 interaction.
-   Advanced fees, complex block triggers (e.g., size-based).
-   Production-grade daemon monitoring/alerting infrastructure.
-   Transaction/block size limits and DoS prevention mechanisms.
-   Formal upgrade/migration framework.

---
