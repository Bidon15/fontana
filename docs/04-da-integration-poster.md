# Phase 4: Celestia DA Integration & Blob Poster Daemon

## Goals

-   Implement the library component for interacting with the Celestia Data Availability layer using `pylestia`.
-   Create the external daemon script responsible for posting locally committed blocks to Celestia.
-   Ensure blocks are marked as fully committed in the DB only after successful DA posting.

## Modules/Files Involved

-   `src/fontana/core/da/celestia.py` (new)
-   `scripts/blob_poster.py` (new)
-   *(Uses)* `pylestia`
-   *(Uses)* `src/fontana/core/db/db.py`
-   *(Uses)* `src/fontana/core/models/`
-   `.env`

## Key Tasks

1.  **Implement DA Interface (`core/da/celestia.py`):**
    *   Create `CelestiaDA` class or functions.
    *   Initialize with Celestia node config (URL, Token, Namespace from `.env` or config object). Validate namespace format.
    *   `post_block(block: Block)`:
        *   Serialize `block.transactions` (e.g., list of `tx.to_sql_row()` -> JSON -> bytes).
        *   Create `pylestia.types.Blob` object with correct namespace and serialized data.
        *   Use `pylestia.node_api.Client` to connect and call `api.blob.submit()`.
        *   Handle potential `pylestia` exceptions (connection errors, submit errors based on `ErrorCode`).
        *   On success, parse the result, format the `blob_ref` string (e.g., `celestia:{height}:{commitment_b64}`).
        *   Return `blob_ref` or raise an exception/return None on failure.
    *   `fetch_block_data(blob_ref: str)`: (Implement basic stub for now, needed in Phase 9) Parse ref, connect to Celestia, fetch blob, deserialize transaction data.
2.  **Implement Blob Poster Daemon (`scripts/blob_poster.py`):**
    *   Import `CelestiaDA` and `db` functions.
    *   Initialize `CelestiaDA` instance.
    *   Use `asyncio` for the main loop.
    *   **Loop Logic:**
        *   `await asyncio.sleep(interval)`.
        *   `uncommitted_blocks = db.fetch_uncommitted_blocks()`.
        *   For each `block` in `uncommitted_blocks`:
            *   `try`:
                *   `blob_ref = await da_poster.post_block(block)`.
                *   If `blob_ref`:
                    *   `db.mark_block_committed(block.header.height, blob_ref)`.
                    *   Log success.
                *   Else (explicit None or handled exception):
                    *   Log failure (block remains uncommitted for next retry).
            *   `except Exception as e`: Log error, continue to next block or wait. Implement basic retry delay within the loop for transient errors.
3.  **Configuration:** Set up `.env` with `CELESTIA_NODE_URL`, `CELESTIA_AUTH_TOKEN` (optional), `CELESTIA_NAMESPACE`.

## Deliverables

-   `CelestiaDA` interface in `core/da/celestia.py`.
-   `scripts/blob_poster.py` runnable daemon script.
-   Configuration via `.env`.

## Testing Strategy

-   **Unit Tests (`tests/`)**:
    *   **CelestiaDA `post_block`:**
        *   Mock the `pylestia.node_api.Client` and its `connect` / `api.blob.submit` methods.
        *   Test successful submission: Verify correct serialization, blob creation, API call parameters. Verify correct `blob_ref` is returned.
        *   Test connection error handling: Mock `client.connect` to raise `ConnectionRefusedError`. Verify `post_block` handles it (e.g., returns None or raises specific exception).
        *   Test submit error handling: Mock `api.blob.submit` to raise `ConnectionError` with specific `ErrorCode` messages (e.g., invalid namespace, blob too big). Verify `post_block` handles these.
    *   **CelestiaDA `fetch_block_data`:** (Basic tests for Phase 9) Mock `pylestia` fetch calls, test parsing of `blob_ref`, test deserialization logic.

-   **Integration Tests (`tests/`)**:
    *   **Poster Daemon Logic (Mocked DA):**
        *   Setup: Test DB with an uncommitted block (created manually or via Phase 3 integration test).
        *   Run: Execute one cycle of the `blob_poster.py` loop logic. **Mock the `CelestiaDA.post_block` method.**
        *   Scenario 1 (DA Success): Mock `post_block` to return a valid `blob_ref`. Assert that `db.mark_block_committed` is called with the correct height and ref. Verify block is now committed in DB.
        *   Scenario 2 (DA Failure): Mock `post_block` to raise an exception or return None. Assert that `db.mark_block_committed` is *not* called. Verify block remains uncommitted in DB.
        *   **Flag:** Requires `TEST_DB_READY=true`.
    *   **Full DA Integration (Requires Running Node):**
        *   Setup: Requires Phase 3 (`block_gen.py`) running. Requires a running Celestia node (local via `celestia-node` or testnet). Configure `.env.dev` with connection details.
        *   Run: Start `block_gen.py` and `blob_poster.py`. Apply transactions to the ledger.
        *   Assertions: Verify blocks are created by `block_gen.py`. Verify `blob_poster.py` picks them up, successfully posts them to the *real* Celestia node, and updates the DB status (`committed=1`, valid `blob_ref`). Manually query the Celestia node (if possible) to confirm blob existence.
        *   **Flag:** Requires `TEST_DB_READY=true` and `CELESTIA_NODE_READY=true`. Provide `TEST_CELESTIA_NODE_URL`, `TEST_CELESTIA_AUTH_TOKEN`, `TEST_CELESTIA_NAMESPACE` in `.env.dev`.

-   **E2E/Scenario Tests:** Becomes part of the full E2E test in later phases.

-   **External Dependency Flags:**
    *   `TEST_DB_READY=true`: For integration tests involving DB state changes.
    *   `CELESTIA_NODE_READY=true`: For integration tests posting to a real Celestia node. Requires associated `TEST_CELESTIA_*` variables in `.env.dev`.