# Phase 6: SDK & Django Plugin (Initial Version)

## Goals

-   Implement a basic Python SDK for consumers to interact with Fontana-powered APIs.
-   Implement a basic Django plugin (`@charge` decorator) for providers to monetize API endpoints.
-   Enable a minimal end-to-end paid API call.

## Modules/Files Involved

-   `src/fontana/sdk/client.py` (new)
-   `src/fontana/django_plugin/decorators.py` (new)
-   `src/fontana/django_plugin/middleware.py` (optional, new)
-   `examples/` (new directory with sample apps)
-   *(Uses)* `src/fontana/wallet/`
-   *(Uses)* `src/fontana/core/ledger/ledger.py` (on provider side)
-   *(Uses)* `src/fontana/core/models/`
-   *(Uses)* HTTP libraries (e.g., `httpx`, `requests`)

## Key Tasks

1.  **Implement Basic SDK (`sdk/client.py`):**
    *   Create `FontanaClient` class (or functions).
    *   Needs access to the *consumer's* `Wallet` instance.
    *   Needs a way to get the consumer's UTXOs (e.g., `get_utxos(address)` function that queries the provider's ledger API endpoint - needs to be created, or assumes direct DB access if co-located - define the access method).
    *   Implement `call_paid_api(provider_url: str, required_amount: float, api_payload: dict)`:
        *   Fetch consumer's UTXOs.
        *   **Simple UTXO Selection:** Find the first available UTXO >= `required_amount` + estimated fee. *No locking or splitting yet.* Raise error if none found.
        *   Construct `SignedTransaction`: Input = selected UTXO. Outputs = payment to provider (address needs to be known/discovered), change back to consumer. Include fee. Hash `api_payload` for `payload_hash`.
        *   Sign the transaction using the consumer's `wallet`.
        *   Use an HTTP client (`httpx` recommended for async) to POST to `provider_url`: include both the `SignedTransaction` (e.g., as JSON in a specific header or body field) and the `api_payload`.
        *   Handle HTTP response: Check for success (e.g., 2xx status). *Defer receipt processing.* Raise exception on payment errors (e.g., 402) or other HTTP errors.
2.  **Implement Basic Django Plugin (`django_plugin/`):**
    *   Create `decorators.py` with `@charge(tia: float)` decorator.
    *   The decorator:
        *   Retrieves the `SignedTransaction` JSON from the incoming `request` (e.g., from headers or body).
        *   Deserializes it into a `SignedTransaction` model.
        *   **Crucially:** Obtains an instance of the provider's `Ledger`.
        *   Calls `ledger.apply_transaction(payment_tx)`.
        *   If `apply_transaction` succeeds: Allow the decorated Django view function to execute.
        *   If `apply_transaction` fails (raises validation/application error): Return an appropriate Django `HttpResponse` (e.g., `HttpResponse(status=402)` for payment required, maybe with error details).
    *   Provider needs to configure the Django app to instantiate/access the `Ledger`.
3.  **Build Example Apps (`examples/`):**
    *   `provider_app/`: Simple Django project, configure settings to use the plugin, create a view decorated with `@charge`. Needs access to a Fontana ledger DB.
    *   `consumer_app/`: Simple Python script using the `sdk` to call the provider app's endpoint. Needs access to a consumer wallet and UTXOs (can manually populate DB for testing).

## Deliverables

-   Basic SDK client capable of selecting a single UTXO, creating/signing TX, and making an HTTP request.
-   Basic Django `@charge` decorator that validates and applies payment transactions using the provider's ledger.
-   Simple working examples demonstrating the flow.

## Testing Strategy

-   **Unit Tests (`tests/`)**:
    *   **SDK:** Test `call_paid_api` logic: Mock UTXO fetching, test UTXO selection (finds first suitable), test transaction construction (correct inputs/outputs/fee/payload hash), mock signing, mock HTTP POST call (verify correct URL, headers, body structure). Test handling of insufficient funds error from UTXO selection. Test handling of HTTP error responses.
    *   **Django Decorator:** Test the decorator logic: Mock the incoming `request` object containing a signed TX. Mock the `Ledger` instance.
        *   Test success case: Mock `ledger.apply_transaction` to return success. Verify the decorated view function is called.
        *   Test failure case: Mock `ledger.apply_transaction` to raise `InsufficientFundsError` or `InvalidSignatureError`. Verify the decorator catches it and returns an `HttpResponse` with status 402 (or similar). Verify the view function is *not* called.

-   **Integration Tests (`tests/`)**:
    *   **SDK <-> Provider (Mocked Ledger):**
        *   Setup: Run the example Django provider app, but configure it to use a *mocked* `Ledger` where `apply_transaction` can be controlled.
        *   Run: Use the SDK (from a test script) to call the provider's endpoint.
        *   Scenario 1 (Success): Configure mock ledger to succeed. Verify SDK gets 2xx response. Verify mock `apply_transaction` was called with the correct TX.
        *   Scenario 2 (Failure): Configure mock ledger to raise an error. Verify SDK receives 4xx response (e.g., 402).
        *   **Flag:** Requires ability to run Django dev server.
    *   **E2E (Requires Running Services):**
        *   Setup: Initialize two separate wallets/DBs (provider, consumer). Fund consumer DB using Phase 5 deposit trigger/mocks. Start the *real* example Django provider app connected to its DB. Start the core daemons (`block_gen`, `blob_poster`) associated with the *provider's* ledger.
        *   Run: Use the example consumer script (or CLI `call`) to invoke the provider API via the SDK.
        *   Assertions: Verify the SDK sends the request. Verify the Django app receives it. Verify `ledger.apply_transaction` on the *provider's* ledger succeeds. Verify the consumer gets a 2xx response. Verify the payment transaction appears in the provider's ledger DB. Verify the transaction eventually gets included in a block and posted to DA by the daemons.
        *   **Flag:** Requires `TEST_DB_READY=true` (for provider and consumer DBs), `DJANGO_APP_READY=true`, potentially `CELESTIA_NODE_READY=true` (if testing DA posting).

-   **External Dependency Flags:**
    *   `TEST_DB_READY=true`: For provider/consumer DBs.
    *   `DJANGO_APP_READY=true`: Indicates the test environment can run the example Django app.
    *   `CELESTIA_NODE_READY=true`: If testing includes actual DA posting during the E2E test.