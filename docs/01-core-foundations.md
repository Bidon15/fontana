# Phase 1: Core Library Foundation

## Goals

-   Establish the foundational data structures (models) for the rollup.
-   Implement the database schema and basic interaction functions.
-   Create the wallet management utilities for key handling and signing.

## Modules Involved

-   `src/fontana/core/models/`
-   `src/fontana/core/db/`
-   `src/fontana/wallet/`

## Key Tasks

1.  **Define Core Models:**
    *   Implement Pydantic models in `core/models/` for `UTXO`, `UTXORef`, `SignedTransaction`, `BlockHeader` (including `state_root: str`), `Block`, `ReceiptProof`, `VaultDeposit`, `VaultWithdrawal`. Ensure correct types and validation.
2.  **Implement Database Layer:**
    *   Define the SQLite schema in `core/db/db.py` reflecting the models.
    *   Implement `init_db()` function to create tables if they don't exist.
    *   Implement CRUD helper functions for each table (e.g., `insert_utxo`, `fetch_unspent_utxos`, `mark_utxo_spent`, `insert_transaction`, `fetch_block_by_height`, `insert_block`, `mark_block_committed`, etc.). Use parameter binding to prevent SQL injection.
3.  **Implement Wallet Utilities:**
    *   Create `wallet/wallet.py` with the `Wallet` class:
        *   `generate()`: Create a new Ed25519 key pair.
        *   `load(path)`: Load key from file.
        *   `save(path)`: Save key to file (ensure secure permissions if possible, though that's often an OS concern).
        *   `get_address()`: Derive public address.
        *   Expose `signing_key` and `verify_key` attributes.
    *   Create `wallet/signer.py` with the `Signer` class:
        *   `sign(message, private_key_bytes)`: Sign data.
        *   `verify(message, signature, public_key_bytes)`: Verify signature.

## Deliverables

-   Completed Pydantic models for all core data types.
-   Functional `core/db/db.py` with schema definition and CRUD functions.
-   Functional `wallet/wallet.py` and `wallet/signer.py` for key management and signing.
-   Initial set of unit tests covering models, DB functions (mocked), and wallet logic.

## Testing Strategy

-   **Unit Tests (`tests/`)**:
    *   **Models:** Test Pydantic model validation (required fields, types, constraints like non-negative amounts). Test serialization/deserialization if custom logic is added.
    *   **Wallet:**
        *   Test `Wallet.generate()` creates valid keys.
        *   Test `Wallet.save()` and `Wallet.load()` roundtrip correctly.
        *   Test `Wallet.get_address()` produces consistent output.
        *   Test `Signer.sign()` produces a signature.
        *   Test `Signer.verify()` successfully verifies a correct signature against the right public key.
        *   Test `Signer.verify()` fails for incorrect signatures, messages, or keys.
    *   **Database:**
        *   Test `init_db()` creates the expected tables (using an in-memory SQLite DB or mocking `sqlite3`).
        *   Test individual CRUD functions: Mock the `sqlite3.connect` and `cursor` objects. Verify that the correct SQL statements are executed with the expected parameters. Check that data transformation logic (e.g., `to_sql_row`, `from_sql_row`) works.

-   **Integration Tests:** None required specifically for this phase, as components are self-contained or easily mockable.

-   **E2E/Scenario Tests:** None required yet.

-   **External Dependency Flags:** None required.