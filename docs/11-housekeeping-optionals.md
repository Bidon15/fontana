# Phase 11: Polish & Optional Features

## Goals

-   Implement selected optional features like advanced fee structures or public proof APIs.
-   Improve robustness, error handling, logging, and monitoring across all components.
-   Refine configurations and documentation.

## Modules/Files Involved

-   Various `src/fontana/` submodules (e.g., `core/ledger`, `core/validation`, `sdk`)
-   Various `scripts/` daemons
-   `docs/`

## Key Tasks (Examples - Choose based on priority)

1.  **Public Merkle Proof API:**
    *   If needed for SDK verification or other external users, implement and expose `ledger.get_utxo_merkle_proof(txid, index, block_height)`. Requires efficient lookup of historical state roots associated with block heights.
2.  **Advanced Fee Logic:**
    *   Implement provider-specific commission rules within `core/ledger` validation.
    *   Potentially add logic for dynamic fees based on rollup congestion.
3.  **Daemon Robustness:**
    *   Improve retry logic in `blob_poster.py`, `vault_watcher.py` (e.g., exponential backoff).
    *   Add more detailed logging with contextual information.
    *   Implement health checks or basic monitoring endpoints for daemons.
    *   Consider persistent queueing for failed DA posts or deposit events.
4.  **Advanced Wallet Management:**
    *   Explore integration with OS keychains or tools like `keyring`.
5.  **Block Trigger Refinement:**
    *   Implement size-based block triggers in `core/sequencing`.
    *   Implement withdrawal-based fast-flushing triggers.
6.  **Documentation:**
    *   Expand user guides, API references, operational procedures.
    *   Document configuration options thoroughly.
7.  **Code Cleanup & Refactoring:** Address any tech debt identified during development. Improve test coverage.

## Deliverables

-   Implemented optional features based on project priorities.
-   Improved logging, error handling, and robustness of daemons.
-   Comprehensive documentation.
-   Refined codebase.

## Testing Strategy

-   **Unit Tests (`tests/`)**: Add tests for any new features (e.g., proof API logic, fee calculations). Add tests for improved error handling paths in daemons (mocking failures).
-   **Integration Tests (`tests/`)**: Add tests verifying new fee logic or block triggers. Test health checks if implemented.
-   **E2E/Scenario Tests (`tests/`)**: Update existing E2E tests or add new ones to cover optional features and verify overall system stability after improvements.
-   **Manual Testing:** Perform exploratory testing on final features. Review logs for clarity.

-   **External Dependency Flags:** Dependent on the features implemented (e.g., `TEST_DB_READY` usually required).
