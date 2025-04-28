# Phase 7: CLI User Commands

## Goals

-   Implement the primary user-facing commands in the Typer CLI.
-   Connect CLI commands to the underlying library functions (SDK, Ledger, Bridge Handlers).
-   Provide basic tools for wallet management, balance checking, API calls, and initiating withdrawals.
-   Include helper commands for triggering bridge events for testing.

## Modules/Files Involved

-   `src/fontana/cli/main.py`
-   *(Uses)* `src/fontana/sdk/client.py`
-   *(Uses)* `src/fontana/core/ledger/ledger.py`
-   *(Uses)* `src/fontana/bridge/handler.py`
-   *(Uses)* `src/fontana/wallet/wallet.py`
-   *(Uses)* `src/fontana/core/db/db.py` (for direct ledger access if SDK isn't ready/suitable)

## Key Tasks

1.  **Refactor `cli/main.py`:** Structure using Typer commands. Load user wallet (`Wallet.load()`) where needed. Instantiate `Ledger` or `SDK Client` as required by commands.
2.  **Implement `init`:** Calls `Wallet.generate()` and `wallet.save()`.
3.  **Implement `show`:** Calls `Wallet.load()` and `wallet.get_address()`.
4.  **Implement `balance`:**
    *   Loads wallet to get address.
    *   Instantiates `Ledger`.
    *   Calls `ledger.get_balance(address)`.
    *   Prints the balance.
5.  **Implement `call`:**
    *   Takes provider URL, amount (maybe inferred from endpoint later), payload path as args.
    *   Loads wallet.
    *   Instantiates `SDK Client` (passing wallet).
    *   Calls `sdk_client.call_paid_api(...)`.
    *   Prints success or error.
6.  **Implement `withdraw`:**
    *   Takes withdrawal amount and L1 recipient address as args.
    *   Loads wallet.
    *   Instantiates `Ledger`.
    *   Fetches UTXOs using `ledger` or `db` functions.
    *   Selects UTXOs to cover the amount + fee.
    *   Constructs a "burn" transaction (Inputs=selected UTXOs, Outputs=empty or specific burn address marker).
    *   Signs the burn transaction.
    *   Calls `ledger.apply_transaction(burn_tx)`.
    *   Prints confirmation that withdrawal *request* is submitted to the rollup ledger (L1 processing is separate).
7.  **Implement `trigger-deposit` (Test Helper):**
    *   Takes amount, recipient rollup address (optional, defaults to loaded wallet) as args.
    *   Generates mock L1 details (fake tx hash, etc.).
    *   Calls `bridge.handler.handle_deposit_received(mock_details)`.
    *   Prints confirmation.
8.  **Implement `trigger-withdrawal-confirm` (Test Helper):**
    *   Takes details identifying the withdrawal (e.g., burn tx hash, user address) and mock L1 confirmation details.
    *   Calls `bridge.handler.handle_withdrawal_confirmed(mock_details)`.
    *   Prints confirmation.

## Deliverables

-   Functional CLI with commands: `init`, `show`, `balance`, `call`, `withdraw`, `trigger-deposit`, `trigger-withdrawal-confirm`.

## Testing Strategy

-   **Unit Tests (`tests/`)**:
    *   For each command function in `cli/main.py`:
        *   Mock the underlying library components (`Wallet`, `Ledger`, `SDK Client`, `Bridge Handler`).
        *   Test that the correct library functions are called with the expected arguments parsed from Typer inputs.
        *   Test basic output formatting.
-   **Integration Tests (`tests/`)**:
    *   **CLI -> Ledger/DB:**
        *   Setup: Initialize test DB/Ledger.
        *   Test `cli init`, `cli show`.
        *   Test `cli trigger-deposit` -> Verify `ledger.process_deposit_event` called and UTXO minted in DB.
        *   Test `cli balance` -> Verify correct balance reported from DB state.
        *   Test `cli withdraw` -> Verify burn TX applied via `ledger.apply_transaction` and input UTXOs marked spent.
        *   Test `cli trigger-withdrawal-confirm` -> Verify `ledger.process_withdrawal_event` called.
        *   **Flag:** Requires `TEST_DB_READY=true`.
    *   **CLI -> SDK -> Provider App (E2E subset):**
        *   Setup: Requires running example provider app (Phase 6), funded consumer wallet/DB.
        *   Run: Use `cli call` targeting the provider app.
        *   Assertions: Verify the call succeeds (2xx response implied) and the payment transaction is applied on the provider's ledger.
        *   **Flag:** Requires `TEST_DB_READY=true`, `DJANGO_APP_READY=true`.

-   **E2E/Scenario Tests:** Use CLI commands as the primary driver for full end-to-end tests involving deposits, calls, withdrawals, block generation, and DA posting.

-   **External Dependency Flags:**
    *   `TEST_DB_READY=true`: For most CLI integration tests.
    *   `DJANGO_APP_READY=true`: For testing `cli call` against a live provider.