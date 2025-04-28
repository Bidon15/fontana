# Phase 3: Block Generation Daemon (`scripts/`)

## Goals

-   Implement the logic for selecting pending transactions and constructing blocks.
-   Create the external script that periodically runs the block generation cycle.
-   Ensure blocks include the correct state root reflecting the transactions within them.

## Modules/Files Involved

-   `scripts/block_gen.py` (new)
-   `src/fontana/core/sequencing/sequencer.py` (new)
-   *(Uses)* `src/fontana/core/ledger/ledger.py`
-   *(Uses)* `src/fontana/core/db/db.py`
-   *(Uses)* `src/fontana/core/models/`

## Key Tasks

1.  **Implement Sequencing Logic (`core/sequencing/sequencer.py`):**
    *   Create a `BlockSequencer` class or functions.
    *   Method `select_transactions(ledger)`: Calls `ledger.get_unconfirmed_txs()`. Implement simple batching rules (e.g., take first N transactions up to a limit, or all transactions if interval passed).
    *   Method `build_block(transactions, ledger, db)`:
        *   Get `prev_hash` from `db.get_latest_block()`.
        *   Determine the `state_root` *after* applying `transactions`. This is tricky. Options:
            *   A) Ledger exposes `calculate_post_batch_state_root(tx_list)` (simulates application).
            *   B) Ledger maintains a *pending* state/tree alongside the committed one.
            *   C) Sequencer simulates the application on a temporary copy of the state tree.
            *   *(Choose an approach - A or C might be simpler initially)*. Assume we get the correct `state_root` for the end of this batch.
        *   Construct `BlockHeader` (with correct `state_root`) and `Block` objects.
        *   Return the constructed `Block`.
2.  **Implement Block Generator Daemon (`scripts/block_gen.py`):**
    *   Import `BlockSequencer`, `Ledger`, `db`.
    *   Initialize `Ledger` instance (needs access to DB/state tree).
    *   Initialize `BlockSequencer`.
    *   Use `asyncio` for the main loop.
    *   **Loop Logic:**
        *   `await asyncio.sleep(interval)`.
        *   Check triggers (time elapsed, maybe check `ledger.get_unconfirmed_txs()` count).
        *   If triggered:
            *   `transactions = sequencer.select_transactions(ledger)`.
            *   If transactions exist:
                *   `new_block = sequencer.build_block(transactions, ledger, db)`.
                *   `block_height = db.insert_block(new_block)` (Inserts with `committed=0`).
                *   `db.mark_transactions_committed([tx.txid for tx in transactions], block_height)`.
                *   Log block creation.
            *   Else: Log "No transactions to sequence".

## Deliverables

-   Sequencing logic encapsulated in `core/sequencing/`.
-   `scripts/block_gen.py` runnable daemon script.
-   Mechanism to run the script (e.g., manual execution, added to `pyproject.toml` later).

## Testing Strategy

-   **Unit Tests (`tests/`)**:
    *   **Sequencing Logic:** Test `select_transactions` batching rules (mocking `ledger.get_unconfirmed_txs`). Test `build_block` correctly constructs the `Block` object with `prev_hash` and `state_root` (mocking DB and ledger state root calls).
-   **Integration Tests (`tests/`)**:
    *   **Block Generation Cycle:**
        *   Setup: Initialize a test DB and Ledger (Phase 2 deliverables needed). Apply several valid transactions using `ledger.apply_transaction`.
        *   Run: Execute one cycle of the `block_gen.py` main loop logic (can extract the core logic into a testable function).
        *   Assertions: Verify a `Block` record is created in the DB. Verify it has the correct `prev_hash` and a plausible `state_root`. Verify the included transactions have their `block_height` updated in the `transactions` table. Verify `ledger.get_unconfirmed_txs()` is now empty (or contains only TXs applied *after* the cycle started).
        *   **Flag:** Requires `TEST_DB_READY=true`.
-   **E2E/Scenario Tests:** None needed specifically for the generator in isolation, but it becomes part of later E2E tests.
-   **External Dependency Flags:**
    *   `TEST_DB_READY=true`: For integration tests.