# Phase 2: Core Ledger Engine (Validation, State Root, Proof Capability)

## Goals

-   Implement the core state transition logic of the rollup within the library.
-   Integrate transaction validation directly into the ledger's application process.
-   Establish the mechanism for calculating state roots based on the UTXO set.
-   Implement the internal capability to generate Merkle proofs for UTXOs (essential for bridging).

## Modules Involved

-   `src/fontana/core/ledger/ledger.py` (new)
-   `src/fontana/core/state_merkle/` (new - e.g., `smt.py` for Sparse Merkle Tree)
-   `src/fontana/core/db/`
-   `src/fontana/wallet/`
-   `src/fontana/core/models/`

## Key Tasks

1.  **Implement State Commitment Structure:**
    *   Create `core/state_merkle/`.
    *   Choose and implement a suitable Merkle tree structure (Sparse Merkle Tree is common for UTXO sets). This needs methods like `update(key, value)`, `get(key)`, `get_root()`, `generate_proof(key)`, `verify_proof(key, value, proof, root)`. The `key` could be `txid:output_index` and `value` could be a hash of UTXO details (recipient, amount). Consider persistence or rebuilding from DB on startup.
2.  **Implement Ledger Class (`core/ledger/ledger.py`):**
    *   Initialize with DB connection info and the state commitment structure (Merkle tree instance).
    *   **Internal Validation Logic:** Implement private helper methods (`_validate_signature`, `_check_inputs_spendable`, `_check_sufficient_funds`) using `core/db` and `wallet.Signer`.
    *   **Implement `apply_transaction(tx)`:**
        *   Call internal validation methods. Raise specific exceptions on failure (e.g., `InvalidSignatureError`, `InsufficientFundsError`, `InputNotFoundError`, `InputSpentError`).
        *   If valid:
            *   Start DB transaction.
            *   Mark input UTXOs as 'spent' in DB (`db.mark_utxo_spent`).
            *   Insert output UTXOs as 'unspent' in DB (`db.insert_utxo`).
            *   **Update the Merkle tree:** Remove input UTXO leaves, add output UTXO leaves.
            *   Commit DB transaction.
            *   Return success. Handle potential DB/Merkle tree errors and rollback DB transaction if needed.
    *   **Implement `get_current_state_root()`:** Return the current root hash from the internal Merkle tree instance.
    *   **Implement `_generate_utxo_proof(txid, index, state_root)`:** Internal method to query the Merkle tree for a proof against a *specific historical root* (tree needs versioning or access to historical roots).
    *   Implement `get_balance(address)` using DB queries.
    *   Implement `get_unconfirmed_txs()` using DB queries.
    *   Implement `process_deposit_event(details)`: Create mint TX, call `self.apply_transaction(mint_tx)`.
    *   Implement `process_withdrawal_event(details)`: Handle post-L1 logic.

## Deliverables

-   A functional Merkle tree implementation (`core/state_merkle/`).
-   A `Ledger` class in `core/ledger/ledger.py` capable of:
    -   Validating transactions against current DB state and signatures.
    -   Atomically applying valid transactions to the DB.
    -   Maintaining a consistent state root via the Merkle tree.
    -   Processing deposit/withdrawal events by applying mint/burn transactions.
    -   Internally generating Merkle proofs for UTXOs (even if not exposed publicly yet).
-   Unit tests for Merkle tree operations (update, root, proof gen/verify).
-   Unit tests for Ledger validation logic (mocking DB/Signer/Tree).
-   Integration tests for `apply_transaction` using a real test DB, verifying DB state changes AND state root updates.

## Testing Strategy

-   **Unit Tests (`tests/`)**:
    *   **Merkle Tree:** Test adding leaves, updating leaves, deleting leaves, root hash calculation, proof generation for inclusion/non-inclusion, proof verification. Use known small examples.
    *   **Ledger Validation:** Mock DB calls (`fetch_unspent_utxos`, etc.) and `Signer.verify`. Test each validation rule in isolation (e.g., test `InsufficientFundsError` is raised correctly).
    *   **Ledger Event Processing:** Test `process_deposit_event` constructs the correct mint TX. Test `process_withdrawal_event` performs expected finalization steps.
    *   **Ledger State Root:** Mock the Merkle tree's `update` method. Verify `apply_transaction` calls it correctly for inputs/outputs. Mock `get_root` and test `get_current_state_root`.
    *   **Ledger Proof Capability:** Mock the Merkle tree's `generate_proof`. Test that `_generate_utxo_proof` calls it with the right parameters.

-   **Integration Tests (`tests/`)**:
    *   **`apply_transaction` Full Flow:**
        *   Setup: Use a real (temporary file or in-memory) SQLite DB, initialize with `init_db`. Initialize a real Merkle tree instance. Instantiate the `Ledger`.
        *   Scenario 1 (Valid TX): Create valid input UTXO(s) in DB/Tree. Create a valid `SignedTransaction`. Call `ledger.apply_transaction()`.
        *   Assertions: Verify input UTXO marked 'spent' in DB. Verify output UTXOs created 'unspent' in DB. Verify the `ledger.get_current_state_root()` changed to the expected new value based on tree updates.
        *   Scenario 2 (Invalid TX - Funds): Setup insufficient input UTXO. Call `ledger.apply_transaction()`. Verify `InsufficientFundsError` (or similar) is raised. Verify DB state and root hash *did not* change.
        *   Scenario 3 (Invalid TX - Spent Input): Setup input UTXO marked 'spent'. Call `ledger.apply_transaction()`. Verify `InputSpentError` (or similar) is raised. Verify DB/root unchanged.
        *   Scenario 4 (Invalid TX - Signature): Call `ledger.apply_transaction()` with a badly signed TX. Verify `InvalidSignatureError` (or similar) is raised. Verify DB/root unchanged.
        *   **Flag:** Requires a writable filesystem for the test DB. Set `TEST_DB_READY=true` in `.env.dev`.

-   **E2E/Scenario Tests:** None required yet.

-   **External Dependency Flags:**
    *   `TEST_DB_READY=true`: For integration tests using a real SQLite database.