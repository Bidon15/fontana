# Phase 9: Withdrawal Processor & Recovery

## Goals

-   Implement the external script to coordinate L1 withdrawal fulfillment based on rollup state.
-   Implement the utility script to recover/verify ledger state from Celestia DA.
-   Ensure withdrawal processing utilizes Merkle proofs for security (assuming the bridge requires them).

## Modules/Files Involved

-   `scripts/withdrawal_processor.py` (new)
-   `scripts/recover_ledger.py` (new utility)
-   *(Uses)* `src/fontana/core/ledger/ledger.py` (especially `_generate_utxo_proof`)
-   *(Uses)* `src/fontana/core/da/celestia.py`
-   *(Uses)* `src/fontana/core/db/db.py`
-   *(Uses)* `src/fontana/bridge/handler.py`
-   *(Uses)* External L1 interaction mechanism (manual or library)

## Key Tasks

1.  **Implement Withdrawal Processor (`scripts/withdrawal_processor.py`):**
    *   Import necessary components (`ledger`, `db`, `bridge.handler`, L1 tool).
    *   Use `asyncio` loop or run as needed.
    *   **Logic:**
        *   Query the ledger/DB for withdrawal requests (e.g., find applied "burn" transactions not yet marked as processed on L1, or query `vault_withdrawals` table for pending requests).
        *   For each pending withdrawal:
            *   Identify the user, amount, L1 recipient address, and the state (block height/state root) *before* the burn transaction was applied.
            *   **Fetch Merkle Proof:** Call the ledger's *internal* proof generation method (`ledger._generate_utxo_proof`) for each burned UTXO against the pre-burn state root.
            *   **Coordinate L1 Transfer:** Use the fetched proofs, state roots, and transaction details to interact with the external bridge component or perform manual steps to authorize the L1 TIA transfer from the vault. *(This interaction is external)*.
            *   **Wait for L1 Confirmation:** Monitor L1 for the withdrawal transaction confirmation.
            *   Upon L1 confirmation:
                *   Gather L1 confirmation details (tx hash, etc.).
                *   Call `bridge.handler.handle_withdrawal_confirmed(...)` to signal the ledger.
                *   Update the `vault_withdrawals` table in the Fontana DB using `db` functions.
    *   Requires configuration for L1 connection/wallet if automating L1 part.
2.  **Implement Recovery Tool (`scripts/recover_ledger.py`):**
    *   Import `ledger`, `db`, `core.da.celestia`.
    *   Use standard Python script structure (not necessarily `asyncio` unless fetching DA is async).
    *   **Arguments:** Starting point (e.g., genesis state or trusted block height/blob_ref), path to DB file. Option to wipe DB (`--wipe`).
    *   **Logic:**
        *   Initialize DB (wipe if requested, run `init_db`).
        *   Initialize `Ledger` (connected to the target DB).
        *   Initialize `CelestiaDA`.
        *   Start from the given height/state.
        *   Loop indefinitely or until current head:
            *   Fetch the next block's `blob_ref` from the DB (if exists) or potentially an external indexer/previous block data.
            *   `block_data = da.fetch_block_data(blob_ref)`.
            *   Deserialize transactions from `block_data`.
            *   `previous_state_root = ledger.get_current_state_root()`.
            *   For each `tx` in `block_data.transactions`:
                *   `ledger.apply_transaction(tx)`. Handle errors - indicates divergence from DA.
            *   `recalculated_state_root = ledger.get_current_state_root()`.
            *   Fetch the actual block header from DA or DB (`db.get_block_header(height)`).
            *   **Verify State Root:** Compare `recalculated_state_root` with `block_header.state_root`. If mismatch, log critical error and potentially halt.
            *   (Optional) Re-insert Block record into DB after successful validation.
            *   Increment height/get next `blob_ref`.
    *   Requires configuration for Celestia node (`.env`).


## Deliverables

-   `scripts/withdrawal_processor.py` script capable of identifying pending withdrawals, fetching proofs, coordinating (manually initially) L1 transfer, and confirming back to the ledger.
-   `scripts/recover_ledger.py` utility script to rebuild and verify ledger state from DA.

## Testing Strategy

-   **Unit Tests (`tests/`)**:
    *   **Withdrawal Processor:** Mock the `Ledger` instance (specifically proof generation methods like `_generate_utxo_proof`), mock `db` queries (like fetching pending withdrawals or burn TXs), mock `bridge.handler` calls, and mock the external L1 confirmation mechanism.
        *   Test identification logic: Ensure it correctly finds relevant withdrawal requests/burn TXs based on DB state.
        *   Test proof fetching call: Verify it calls the (mocked) ledger's proof generation with the correct parameters (UTXO IDs, pre-burn state root/height).
        *   Test confirmation logic: Verify it calls `bridge.handler.handle_withdrawal_confirmed` after the (mocked) L1 confirmation step. Verify it calls `db` functions to update the `vault_withdrawals` table.
    *   **Recovery Tool:** Mock `CelestiaDA.fetch_block_data` to return pre-defined block transaction data. Mock `Ledger.apply_transaction` (to check if it's called correctly) and `Ledger.get_current_state_root`.
        *   Test the main recovery loop logic: Verify it iterates through blob refs correctly.
        *   Test transaction replay: Ensure `apply_transaction` is called for every transaction in the mock block data, in the correct order.
        *   Test state root verification: Provide mock block headers with state roots. Verify the script correctly compares the recalculated root from the mock ledger with the header's root and logs errors/success appropriately.
        *   Test `--wipe` argument functionality (mock `db.init_db` and check if wipe logic is triggered).

-   **Integration Tests (`tests/`)**:
    *   **Withdrawal Proof Fetching:**
        *   Setup: Initialize a test DB and `Ledger`. Apply transactions, including a valid burn transaction for a withdrawal. Note the state root *before* the burn.
        *   Run: Instantiate the `Ledger`. Call the *internal* proof generation method (`_generate_utxo_proof` or similar) directly, passing the burned UTXO details and the pre-burn state root.
        *   Assertions: Verify a non-empty, structurally valid Merkle proof is returned. Optionally, if the Merkle tree implementation allows, verify the returned proof against the pre-burn state root and the UTXO data.
        *   **Flag:** Requires `TEST_DB_READY=true`.
    *   **Withdrawal Processor -> Handler -> Ledger Confirmation:**
        *   Setup: Test DB/Ledger with an applied burn TX, representing a pending withdrawal.
        *   Run: Execute the core logic of `withdrawal_processor.py` (find pending -> fetch mock proof -> mock L1 success -> call handler).
        *   Assertions: Verify `bridge.handler.handle_withdrawal_confirmed` is called. Verify `ledger.process_withdrawal_event` (called by the handler) executes its logic (e.g., logging, final state updates if any). Verify the corresponding `vault_withdrawals` record in the DB is updated correctly (e.g., marked processed, L1 TX hash stored).
        *   **Flag:** Requires `TEST_DB_READY=true`.
    *   **Recovery Tool Full Replay & Verification:**
        *   Setup:
            *   Create a populated test DB by running previous phases' tests or a dedicated setup script (apply deposits, transfers, burns).
            *   Run `block_gen.py` and `blob_poster.py` (mocking DA `post_block`) to generate blocks with state roots and get mock `blob_ref`s (e.g., `mock_blob_1`, `mock_blob_2`). Mark blocks as committed in the DB.
            *   For each mock `blob_ref`, store the corresponding serialized transaction list (the data that *would* be posted) in test fixture files or memory.
            *   Save a copy/snapshot of the final, correct DB state and final state root.
        *   Run: Execute `scripts/recover_ledger.py --wipe` targeting a *new, empty* DB file. Provide the starting point (genesis or first mock `blob_ref`). Mock `CelestiaDA.fetch_block_data` to return the saved transaction list fixtures based on the requested mock `blob_ref`.
        *   Assertions:
            *   Verify the script runs without state root mismatch errors.
            *   Verify the final state root in the recovered ledger matches the final state root of the original DB.
            *   Compare the entire content (or key tables/balances) of the recovered DB with the saved snapshot of the original DB – they should be identical.
        *   **Flag:** Requires `TEST_DB_READY=true`.

-   **E2E/Scenario Tests:** A full withdrawal scenario would involve: `cli withdraw` -> `block_gen` includes burn TX -> `blob_poster` posts block -> `withdrawal_processor` detects -> (Manual/Mock L1 TX) -> `withdrawal_processor` confirms -> Final state check.

-   **External Dependency Flags:**
    *   `TEST_DB_READY=true`: For all integration tests involving the database.