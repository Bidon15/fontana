# Phase 5: Vault Watcher & Bridge Interface

## Goals

-   Implement the external daemon script responsible for monitoring the L1 bridge/vault for deposits.
-   Define and implement the Python library interface (`src/fontana/bridge`) that external components (like the vault watcher or future Rust bridge) use to signal events to the core ledger.
-   Connect the vault watcher daemon to the bridge interface to trigger deposit processing in the ledger.

## Modules/Files Involved

-   `scripts/vault_watcher.py` (new)
-   `src/fontana/bridge/handler.py` (new)
-   *(Uses)* `pylestia` (or other L1 interaction library/method)
-   *(Uses)* `src/fontana/core/ledger/ledger.py`
-   *(Uses)* `src/fontana/core/db/db.py`
-   *(Uses)* `src/fontana/core/models/`

## Key Tasks

1.  **Define Bridge Interface (`src/fontana/bridge/handler.py`):**
    *   Create the file.
    *   Define `handle_deposit_received(deposit_details: dict)`:
        *   Takes parsed deposit information (e.g., L1 tx hash, recipient rollup address, amount, L1 block height/timestamp).
        *   Instantiates a `Ledger` object (or gets a shared instance).
        *   Calls `ledger.process_deposit_event(deposit_details)`.
        *   Includes logging.
    *   Define `handle_withdrawal_confirmed(withdrawal_details: dict)`:
        *   Takes details of a confirmed L1 withdrawal (e.g., corresponding burn TX info, L1 tx hash).
        *   Calls `ledger.process_withdrawal_event(withdrawal_details)`.
        *   Includes logging.
2.  **Implement Vault Watcher Daemon (`scripts/vault_watcher.py`):**
    *   Import `bridge.handler`, `db` functions, L1 interaction method.
    *   Use `asyncio` for the main loop.
    *   **L1 Monitoring Logic:**
        *   Implement mechanism to watch the designated L1 vault address. Options:
            *   Use `pylestia` state queries if monitoring a standard account for simple transfers (less robust for contract interactions).
            *   Use a dedicated L1 SDK/library (e.g., `cosmpy`, `web3.py` if vault is EVM-based) to query transactions or events.
            *   **(Future):** This script might be replaced or simplified if the Rust bridge handles direct L1 monitoring.
        *   Requires configuration for L1 node URL and vault address (`.env`).
    *   **Event Parsing:** Extract relevant details (sender - might be hard, recipient note/memo -> rollup address, amount, L1 tx hash, height) from detected L1 deposit transactions/events.
    *   **DB Recording & Triggering:**
        *   For each valid deposit detected:
            *   Check if L1 TX hash already processed in `vault_deposits` table to prevent duplicates.
            *   `db.insert_vault_deposit(...)` to record the raw event.
            *   Call `bridge.handler.handle_deposit_received(...)` with the parsed details.
    *   Include error handling for L1 connection issues and parsing errors.

## Deliverables

-   `src/fontana/bridge/handler.py` defining the interface functions.
-   `scripts/vault_watcher.py` runnable daemon script.
-   Configuration options in `.env` for L1 node and vault address.

## Testing Strategy

-   **Unit Tests (`tests/`)**:
    *   **Bridge Handler:** Mock the `Ledger` instance. Test `handle_deposit_received` calls `ledger.process_deposit_event` with correctly formatted arguments. Test `handle_withdrawal_confirmed` calls `ledger.process_withdrawal_event`.
    *   **Vault Watcher Logic:** Mock the L1 interaction library/API calls.
        *   Test successful deposit detection: Provide mock L1 data, verify correct parsing and that `db.insert_vault_deposit` and `bridge.handler.handle_deposit_received` are called.
        *   Test duplicate deposit handling: Verify that if a deposit with the same L1 tx hash is seen again, it's ignored.
        *   Test parsing error handling.
        *   Test L1 connection error handling.

-   **Integration Tests (`tests/`)**:
    *   **Watcher -> Handler -> Ledger:**
        *   Setup: Initialize test DB and Ledger.
        *   Run: Execute the core logic of `vault_watcher.py` (parsing + triggering part), providing it with mock L1 deposit data.
        *   Assertions: Verify a `VaultDeposit` record is created in the DB. Verify `ledger.process_deposit_event` was called (check for side effects like minted UTXOs and state root change).
        *   **Flag:** Requires `TEST_DB_READY=true`.
    *   **(Optional) Watcher -> Real L1:**
        *   Setup: Requires a running L1 testnet node and a configured vault address. Configure `.env.dev` with L1 details.
        *   Run: Start the `vault_watcher.py` daemon against the testnet L1. Manually send a deposit transaction to the vault address on the testnet L1.
        *   Assertions: Verify the watcher detects the transaction, creates the DB record, and calls the handler.
        *   **Flag:** Requires `TEST_DB_READY=true` and `L1_NODE_READY=true`. Provide `TEST_L1_NODE_URL`, `TEST_L1_VAULT_ADDRESS` in `.env.dev`.

-   **E2E/Scenario Tests:** Deposit flow becomes part of the full E2E test.

-   **External Dependency Flags:**
    *   `TEST_DB_READY=true`: For integration tests involving DB state.
    *   `L1_NODE_READY=true`: For optional integration tests against a real L1 node. Requires associated `TEST_L1_*` variables in `.env.dev`.