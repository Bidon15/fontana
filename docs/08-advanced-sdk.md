# Phase 8: Advanced SDK & Concurrency

## Goals

-   Enhance the Python SDK (`src/fontana/sdk`) to handle real-world complexities like concurrent API calls and efficient UTXO management.
-   Implement UTXO caching, locking, and Just-in-Time (JIT) splitting.

## Modules/Files Involved

-   `src/fontana/sdk/client.py`
-   `src/fontana/sdk/cache.py` (new, optional abstraction)
-   `src/fontana/sdk/locking.py` (new, optional abstraction)
-   *(Uses)* `src/fontana/core/ledger/ledger.py` (or API endpoint for submitting split TX)
-   *(Uses)* `src/fontana/wallet/wallet.py`
-   *(Uses)* `asyncio` (for locking)

## Key Tasks

1.  **Implement UTXO Cache:**
    *   Design a cache (in-memory dict initially, potentially persistent later) within the `SDK Client` or a separate `cache.py`.
    *   Store UTXOs fetched for the consumer, keyed by `txid:index`. Include status (available, locked, potentially pending confirmation after split).
    *   Implement logic to refresh the cache periodically or on demand by querying the ledger state (needs access method).
2.  **Implement UTXO Locking:**
    *   Use `asyncio.Lock` associated with each UTXO entry in the cache or a global lock with finer-grained checks.
    *   Modify `call_paid_api`: Before selecting a UTXO, attempt to acquire its lock. Release the lock after the API call completes (success or failure) or after determining the UTXO won't be used. Handle timeouts waiting for locks.
3.  **Implement UTXO Selection Strategy:**
    *   Enhance the selection logic: Instead of the first suitable UTXO, find the *smallest* available (unlocked) UTXO that meets the `amount + fee` requirement to minimize fragmentation.
4.  **Implement JIT Splitting Logic:**
    *   If the selection strategy finds no single suitable UTXO, but the *total* available balance is sufficient:
        *   Select a larger available (unlocked) UTXO to split. Acquire its lock.
        *   Construct a "split transaction": Input = large UTXO. Outputs = multiple smaller UTXOs (e.g., one just large enough for the current call, others based on some strategy) + change back to self.
        *   Sign the split transaction.
        *   **Submit the split transaction:** This needs a way to send transactions directly to the ledger *without* an associated API call (e.g., a dedicated ledger endpoint or direct access if co-located).
        *   **Wait for Confirmation:** Poll the ledger state (via `get_utxo_status` or similar query) until one of the new small output UTXOs from the split transaction appears as 'unspent'. This requires the ledger to process the split TX relatively quickly. Handle timeouts.
        *   Release the lock on the original large (now spent) UTXO.
        *   Acquire the lock for the newly created small UTXO.
        *   Use this new small UTXO for the original `call_paid_api` request (construct payment TX, sign, send to provider).
        *   Release the small UTXO lock after the API call.
5.  **Refactor `call_paid_api`:** Integrate caching, locking, selection, and splitting logic into a coherent flow.

## Deliverables

-   Enhanced `SDK Client` with UTXO caching, locking, and JIT splitting capabilities.

## Testing Strategy

-   **Unit Tests (`tests/`)**:
    *   **Cache:** Test adding, retrieving, updating, removing UTXOs from the cache. Test refresh logic (mocking ledger queries).
    *   **Locking:** Test acquiring/releasing locks. Simulate contention scenarios using multiple `asyncio` tasks trying to lock the same UTXO.
    *   **Selection:** Test the strategy correctly picks the smallest sufficient UTXO among available/unlocked ones.
    *   **Splitting:** Test the split transaction construction logic (correct inputs/outputs). Test the polling logic for split confirmation (mocking ledger state changes).

-   **Integration Tests (`tests/`)**:
    *   **JIT Splitting Full Flow:**
        *   Setup: Test DB/Ledger with only large UTXOs available for a consumer wallet.
        *   Run: Use the SDK's `call_paid_api` requiring an amount smaller than any available UTXO.
        *   Assertions: Verify the SDK constructs and submits a split transaction to the ledger (check DB/ledger state). Verify the SDK polls and detects the new UTXO. Verify the SDK then constructs the payment transaction using the new UTXO and attempts the API call (mock the final HTTP call). Verify locks are acquired/released correctly.
        *   **Flag:** Requires `TEST_DB_READY=true`. Needs a way for SDK test to submit split TX to the ledger instance.
    *   **Concurrency Test:**
        *   Setup: Test DB/Ledger with a limited set of UTXOs.
        *   Run: Launch multiple (`asyncio.gather`) concurrent `call_paid_api` tasks using the SDK, targeting a mock provider endpoint. Ensure total required amount exceeds individual UTXOs but not total balance, forcing splits and contention.
        *   Assertions: Verify all calls eventually succeed or fail predictably (e.g., insufficient funds if total is exceeded). Verify no race conditions occur (e.g., double-spending the same UTXO). Check lock acquisition/release patterns.
        *   **Flag:** Requires `TEST_DB_READY=true`.

-   **E2E/Scenario Tests:** Run E2E tests with multiple concurrent consumers.

-   **External Dependency Flags:**
    *   `TEST_DB_READY=true`: For tests involving ledger state and split transaction submission.