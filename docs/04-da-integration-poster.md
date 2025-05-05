# Phase 4: Celestia DA Integration & Blob Poster Daemon

## Goals

-   Implement the library component for interacting with the Celestia Data Availability layer using the `pylestia` Rust extension.
-   Create the external daemon script responsible for posting locally committed blocks to Celestia.
-   Ensure blocks are marked as fully committed in the DB only after successful DA posting.

## Implementation Details

-   `src/fontana/core/da/client.py` - CelestiaClient implementation
-   `src/fontana/core/da/poster.py` - BlobPoster daemon
-   `src/fontana/core/da/pylestia/` - Pylestia Rust extension as a submodule

## Key Features

### CelestiaClient (`client.py`)

- **Class**: `CelestiaClient`
  - Initializes with Celestia node configuration (URL, Token, Namespace)
  - Manages namespaces to ensure they're valid 8-byte hex values
  - Handles posting blocks to Celestia and checking their confirmation status
  - Abstracts away the complexities of the pylestia Rust extension

- **Key Methods**:
  - `post_block(block: Block) -> Optional[str]`: Posts a block to Celestia and returns a blob reference
  - `check_confirmation(namespace_id: str) -> bool`: Checks if a previously submitted blob has been confirmed
  - `fetch_block_data(blob_ref: str) -> Optional[Block]`: Retrieves block data from Celestia using a blob reference
  - `_namespace_id_bytes(namespace_id: str) -> bytes`: Converts a namespace ID to bytes
  - `_get_namespace_for_block(block_height: int) -> str`: Generates a unique namespace ID for a block

### BlobPoster Daemon (`poster.py`)

- **Class**: `BlobPoster`
  - Runs as a background daemon to post blocks to Celestia
  - Manages a retry queue for failed submissions
  - Updates the database with blob references when submissions succeed

- **Key Methods**:
  - `fetch_uncommitted_blocks() -> List[Block]`: Retrieves blocks that haven't been submitted to Celestia
  - `post_block_to_celestia(block: Block) -> Optional[str]`: Posts a block to Celestia with retry logic
  - `mark_block_committed(block_height: int, blob_ref: str) -> bool`: Updates the database after successful submission
  - `run()`: Main loop that continuously processes uncommitted blocks
  - `process_retry_queue()`: Handles failed submissions that need to be retried

### Pylestia Integration

- The integration uses the Pylestia Rust extension to communicate with Celestia nodes
- Pylestia is included as a submodule in `src/fontana/core/da/pylestia/`
- The extension must be built using Maturin before use: `maturin develop --release`
- Requires proper namespace handling (valid 8-byte hex values) for the Rust extension

## Configuration

The Celestia integration can be configured through the following environment variables:

- `CELESTIA_NODE_URL`: URL of the Celestia node (required)
- `CELESTIA_AUTH_TOKEN`: Authentication token for the Celestia node (required)
- `CELESTIA_NAMESPACE`: Base namespace for Fontana (default: "fontana")
- `CELESTIA_CONFIRMATION_BLOCKS`: Number of blocks to wait for confirmation (default: 2)

## Modules/Files Involved

-   `src/fontana/core/da/client.py` (new)
-   `src/fontana/core/da/poster.py` (new)
-   *(Uses)* `pylestia`
-   *(Uses)* `src/fontana/core/db/db.py`
-   *(Uses)* `src/fontana/core/models/`
-   `.env`

## Key Tasks

1.  **Implement DA Interface (`core/da/client.py`):**
    *   Create `CelestiaClient` class or functions.
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
    *   Import `CelestiaClient` and `db` functions.
    *   Initialize `CelestiaClient` instance.
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

## Deliverables

-   `CelestiaClient` interface in `core/da/client.py`.
-   `scripts/blob_poster.py` runnable daemon script.
-   Configuration via `.env`.

## Testing Strategy

-   **Unit Tests (`tests/`)**:
    *   **CelestiaClient `post_block`:**
        *   Mock the `pylestia.node_api.Client` and its `connect` / `api.blob.submit` methods.
        *   Test successful submission: Verify correct serialization, blob creation, API call parameters. Verify correct `blob_ref` is returned.
        *   Test connection error handling: Mock `client.connect` to raise `ConnectionRefusedError`. Verify `post_block` handles it (e.g., returns None or raises specific exception).
        *   Test submit error handling: Mock `api.blob.submit` to raise `ConnectionError` with specific `ErrorCode` messages (e.g., invalid namespace, blob too big). Verify `post_block` handles these.
    *   **CelestiaClient `fetch_block_data`:** (Basic tests for Phase 9) Mock `pylestia` fetch calls, test parsing of `blob_ref`, test deserialization logic.

-   **Integration Tests (`tests/`)**:
    *   **Poster Daemon Logic (Mocked DA):**
        *   Setup: Test DB with an uncommitted block (created manually or via Phase 3 integration test).
        *   Run: Execute one cycle of the `blob_poster.py` loop logic. **Mock the `CelestiaClient.post_block` method.**
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