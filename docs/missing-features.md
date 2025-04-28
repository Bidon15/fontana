# Fontana - Missing Features Implementation Flow

This flow incorporates genesis state, unified configuration, provider composability notes, provisional receipts, empty block logic, monitoring points, and clarifies error handling/upgrade approach. Validation and Merkle proofs are integrated into the ledger.

---

## Phase 1: Core Library Foundation (Models, DB, Wallet, Config)

*   **Goal:** Establish core models, DB, wallet utilities, **and standardized configuration loading**. Define **genesis state**.
*   **Modules Involved:** `src/fontana/core/models/`, `src/fontana/core/db/`, `src/fontana/wallet/`, `src/fontana/core/config.py` (new)
*   **Deliverables:**
    *   Pydantic models (including `state_root` in `BlockHeader`).
    *   DB schema/functions (`init_db`, CRUD).
    *   Wallet utilities.
    *   **`core/config.py`:** Pydantic `BaseSettings` model loading from `.env`.
    *   **Genesis Definition:** Documented structure for initial state (e.g., in a `genesis.json` format definition).
    *   Unit tests.

---

## Phase 2: Core Ledger Engine (Validation, State Root, Proof Capability)

*   **Goal:** Implement ledger logic including validation, state updates, event processing, state root calculation, and **internal Merkle proof generation capability**.
*   **Modules Involved:** `src/fontana/core/ledger/ledger.py`, `src/fontana/core/state_merkle/` (new), `src/fontana/core/db/`, `src/fontana/wallet/`, `src/fontana/core/config.py`
*   **Deliverables:**
    *   Merkle tree implementation (`core/state_merkle/`).
    *   `Ledger` class using `core/config`, performing validation, atomic DB/Merkle updates via `apply_transaction`, processing events, providing state queries (`get_current_state_root`), and internal proof generation (`_generate_utxo_proof`).
    *   Unit and Integration tests (Requires `TEST_DB_READY=true`).

---

## Phase 3: Genesis Utility & Block Generator Daemon (`scripts/`)

*   **Goal:** Implement the genesis creation utility and the external daemon for sequencing blocks (including empty ones).
*   **Files/Modules Involved:** `scripts/create_genesis.py` (new), `scripts/block_gen.py`, `src/fontana/core/sequencing/`, `src/fontana/core/ledger/`, `src/fontana/core/db/`, `src/fontana/core/config.py`
*   **Deliverables:**
    *   `scripts/create_genesis.py`: Reads genesis definition, initializes DB (runs `init_db`, inserts genesis UTXOs via ledger/db, creates Block 0 record with initial state root).
    *   Sequencing logic in `core/sequencing/`.
    *   `scripts/block_gen.py` daemon driving sequencing, **generating empty blocks if no TXs are present based on time trigger (e.g., ~6s)**, fetching state root, committing block locally (`committed=0`). Uses `core/config`.
    *   Tests for genesis utility. Tests verifying block generation (including empty blocks) with correct state roots (Requires `TEST_DB_READY=true`).

---

## Phase 4: Celestia DA Integration & Blob Poster Daemon (`src/fontana/core/da/`, `scripts/`)

*   **Goal:** Implement Celestia posting logic and the external daemon, handling posting failures robustly.
*   **Files/Modules Involved:** `src/fontana/core/da/celestia.py`, `scripts/blob_poster.py`, `pylestia`, `.env`, `src/fontana/core/config.py`
*   **Deliverables:**
    *   `core/da/celestia.py` with `post_block()` (posts data for non-empty blocks, maybe minimal data for empty blocks) and `fetch_block_data()`. Uses `core/config`.
    *   `scripts/blob_poster.py` daemon polling for uncommitted blocks (including empty), calling `post_block()`, updating DB status. **Implements retries and logs critical errors/alerts on persistent failure (no automatic rollback).** Uses `core/config`.
    *   Tests verifying posting (including empty blocks) and DB updates. Integration tests for failure handling (Requires `TEST_DB_READY=true`, `CELESTIA_NODE_READY=true` for full test).

---

## Phase 5: Vault Watcher & Bridge Interface (`scripts/`, `src/fontana/bridge/`)

*   **Goal:** Implement the vault watcher daemon and the library interface for bridge events.
*   **Files/Modules Involved:** `scripts/vault_watcher.py`, `src/fontana/bridge/handler.py`, `pylestia`/L1 lib, `src/fontana/core/ledger/`, `src/fontana/core/db/`, `src/fontana/core/config.py`
*   **Deliverables:**
    *   `bridge/handler.py` interface functions.
    *   `scripts/vault_watcher.py` daemon monitoring L1, calling handler on deposit events. Uses `core/config`.
    *   Tests verifying deposit event handling triggers ledger updates. (Requires `TEST_DB_READY=true`, potentially `L1_NODE_READY=true`).

---

## Phase 6: SDK & Django Plugin (Initial Version) (`src/fontana/sdk/`, `src/fontana/django_plugin/`)

*   **Goal:** Build initial library components for API consumers and providers, implementing **provisional receipts** and considering **provider composability**.
*   **Files/Modules Involved:** `src/fontana/sdk/client.py`, `src/fontana/django_plugin/`, `examples/`
*   **Deliverables:**
    *   Basic SDK `call_paid_api`. **Design note on how providers use SDK logic.**
    *   Basic Django `@charge` decorator calling `ledger.apply_transaction`. **Returns provisional receipt** referencing local block commit info.
    *   Example apps.
    *   E2E tests verifying provisional receipts and payment flow. (Requires `TEST_DB_READY=true`, `DJANGO_APP_READY=true`).

---

## Phase 7: CLI User Commands (`src/fontana/cli/`)

*   **Goal:** Implement user-facing CLI commands using library components and unified config.
*   **Files/Modules Involved:** `src/fontana/cli/main.py`, uses other `src/fontana/` components.
*   **Deliverables:** Functional CLI commands (`init`, `show`, `balance`, `call`, `withdraw`, test triggers). Tests for CLI commands (Requires `TEST_DB_READY=true`).

---

## Phase 8: Advanced SDK & Concurrency (`src/fontana/sdk/`)

*   **Goal:** Make the SDK robust for concurrent use.
*   **Files/Modules Involved:** `src/fontana/sdk/client.py`
*   **Deliverables:** SDK with caching, locking, splitting. Concurrency tests (Requires `TEST_DB_READY=true`).

---

## Phase 9: Withdrawal Processor & Recovery (`scripts/`, `src/fontana/core/`)

*   **Goal:** Implement withdrawal coordination (using proofs) and ledger recovery.
*   **Files/Modules Involved:** `scripts/withdrawal_processor.py`, `scripts/recover_ledger.py`, uses core library components.
*   **Deliverables:**
    *   Withdrawal processor script (fetches proofs via `ledger._generate_utxo_proof`, coordinates L1 TX, calls handler).
    *   Recovery utility script (replays TXs, verifies state roots).
    *   Tests verifying proof fetching and recovery root verification (Requires `TEST_DB_READY=true`).

---

## Phase 10: Rust Bridge Integration (`rust/`, `src/fontana/bridge/`)

*   **Goal:** Integrate the actual Rust bridge component, including proof requests.
*   **Files/Modules Involved:** `rust/`, bindings, `src/fontana/bridge/handler.py`, `src/fontana/core/ledger/`
*   **Deliverables:** Compiled Rust bridge, integrated build system. **Rust bridge calls Python `ledger` to get Merkle proofs.** E2E tests with Rust bridge (Requires multiple flags including `RUST_BRIDGE_READY=true`).

---

## Phase 11: Polish & Optional Features

*   **Goal:** Add monitoring, potentially public proof API, refine error handling. Mark upgrades TBD. Exclude DoS limits.
*   **Files/Modules Involved:** Various `src/fontana/`, `scripts/`
*   **Deliverables:**
    *   **Prometheus metric endpoints/hooks** in key areas (daemons, ledger).
    *   (Optional) Public API in `ledger` for proofs.
    *   Improved logging/alerting in daemons for persistent errors.
    *   Documentation update marking upgrades as TBD.
    *   Final code cleanup.
    *   Tests for new features and monitoring points.

---
