# Phase 10: Rust Bridge Integration

## Goals

-   Replace mock bridge interactions with a real Rust bridge component (e.g., using Hyperlane SDK).
-   Establish bidirectional communication: Rust calls Python handlers for L1 events, Python ledger provides proofs to Rust for L1 verification.
-   Integrate the Rust build process using `maturin`.

## Modules/Files Involved

-   `rust/` (new directory containing Rust crate)
    -   `Cargo.toml`
    *   `src/lib.rs` (main library file with PyO3 bindings)
    *   Other Rust modules for bridge logic.
-   `pyproject.toml` (updated for `maturin` build)
-   `src/fontana/bridge/handler.py` (used by Rust via bindings)
-   `src/fontana/core/ledger/ledger.py` (called by Rust via bindings to get proofs)
-   `scripts/withdrawal_processor.py` (potentially simplified or removed if Rust handles coordination)

## Key Tasks

1.  **Develop Rust Bridge Component (`rust/`):**
    *   Implement core Hyperlane (or chosen technology) logic for monitoring the L1 vault contract/address.
    *   Implement logic to parse L1 deposit events.
    *   Implement logic to construct and submit L1 withdrawal transactions. Requires secure L1 private key management (outside the scope of Fontana library itself, likely handled by the environment running the Rust component).
    *   **Implement state verification:** Before submitting a withdrawal TX to L1, the Rust component needs to verify the withdrawal request against the Fontana rollup state. This involves:
        *   Obtaining the relevant Fontana block headers (containing state roots) - potentially via Fontana API or DA.
        *   Calling into the Python `Ledger` (via PyO3 binding) to request Merkle proofs for the UTXOs being burned, verifying them against the appropriate state root.
2.  **Implement PyO3 Bindings (`rust/src/lib.rs`):**
    *   Expose Rust functions callable from Python (if needed, maybe less common).
    *   Expose Python functions callable from Rust:
        *   Create Rust wrappers that acquire the Python GIL and call the functions defined in `src/fontana/bridge/handler.py` (e.g., `handle_deposit_received`, `handle_withdrawal_confirmed`). Pass necessary data from Rust (L1 event details) to Python.
        *   Create Rust wrappers to call Python `Ledger` methods, specifically to request Merkle proofs (e.g., `get_utxo_merkle_proof(txid, index, state_root)`). This requires passing state root/version info from Rust to Python.
3.  **Configure Build System:**
    *   Set up `rust/Cargo.toml` with dependencies (PyO3, Hyperlane SDK, L1 client, etc.).
    *   Configure `pyproject.toml` (`[tool.maturin]` section) to build the Rust code in `rust/` as a Python extension module installable alongside the `src/fontana` package.
4.  **Integrate Python Side:**
    *   Ensure `bridge/handler.py` functions handle data passed from Rust correctly.
    *   Expose a mechanism for the Rust bindings to access an instance of the `Ledger` (e.g., via a shared context, a global instance if safe, or specific setup during initialization). Implement the public `ledger.get_utxo_merkle_proof` if needed for the binding.
    *   Potentially refactor/remove parts of `scripts/vault_watcher.py` and `scripts/withdrawal_processor.py` if the Rust component takes over direct L1 monitoring and coordination. The Python handlers in `bridge/handler.py` remain the crucial interface points.

## Deliverables

-   Compiled Rust shared object/extension module (`*.so` or `*.pyd`).
-   Updated `pyproject.toml` and build instructions incorporating `maturin`.
-   Working bidirectional communication between the Rust bridge and the Python Fontana library.
-   End-to-end deposit and withdrawal flows processed via the integrated Rust bridge.

## Testing Strategy

-   **Rust Unit Tests (`rust/tests/`):** Test Rust logic independently (L1 parsing, transaction construction, proof verification logic using mock proofs).
-   **Python Unit Tests (`tests/`):** Test `bridge/handler.py` functions assuming they are called with data structures originating from Rust (mock the calls). Test the newly exposed `ledger.get_utxo_merkle_proof` method.
-   **Integration Tests (`tests/`) - Python/Rust Bindings:**
    *   Setup: Build the Rust extension (`maturin develop`).
    *   Test Rust -> Python calls: Write Python test code that simulates the Rust component calling `bridge.handler.handle_deposit_received` and `handle_withdrawal_confirmed`. Verify the Python handlers execute correctly and trigger the appropriate ledger actions (mocking the ledger if necessary).
    *   Test Python -> Rust calls (Proof Request): Write Python test code that instantiates the `Ledger`. Write Rust test code (callable via Python test) that requests a Merkle proof from the Python `Ledger` instance via the bindings. Verify the proof is correctly passed back to Rust.
    *   **Flag:** Requires `RUST_EXTENSION_BUILT=true`.
-   **End-to-End Tests (Full System):**
    *   Setup: Requires running L1 testnet node, deployed bridge contracts (Hyperlane), running compiled Rust bridge component, running Python core daemons (`block_gen`, `blob_poster`), configured `.env.dev` for all connections. Initialize Fontana DB.
    *   Scenario (Deposit): Send deposit TX on L1 testnet -> Verify Rust bridge detects -> Verify Rust calls Python `handle_deposit_received` -> Verify Fontana ledger mints UTXO -> Verify state root updates -> Verify block generated/posted.
    *   Scenario (Withdrawal): Initiate withdrawal on Fontana (`cli withdraw` -> burn TX applied) -> Verify Rust bridge detects/requests verification -> Verify Rust calls Python `ledger.get_utxo_merkle_proof` -> Verify Rust uses proof to submit L1 withdrawal TX -> Verify L1 TX succeeds -> Verify Rust calls Python `handle_withdrawal_confirmed` -> Verify Fontana withdrawal record finalized.
    *   **Flag:** Requires `TEST_DB_READY=true`, `L1_NODE_READY=true`, `CELESTIA_NODE_READY=true`, `RUST_BRIDGE_READY=true`.

-   **External Dependency Flags:**
    *   `RUST_EXTENSION_BUILT=true`: For Python tests involving direct calls through the bindings.
    *   `TEST_DB_READY=true`, `L1_NODE_READY=true`, `CELESTIA_NODE_READY=true`, `RUST_BRIDGE_READY=true`: For full end-to-end system tests.
