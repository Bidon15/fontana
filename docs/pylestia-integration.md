# Pylestia Integration Guide

This document explains how Fontana integrates with Celestia's Data Availability (DA) layer using the pylestia Rust extension.

## Overview

Pylestia is a Python binding for the Celestia blockchain, providing access to all Celestia node API endpoints directly from Python. It's implemented as a Rust extension using PyO3, which means it requires compilation before use.

In Fontana, pylestia is integrated as a Git submodule rather than a PyPI package dependency to ensure complete control over the version and build process.

## Setup and Installation

### Clone with Submodules

When cloning the Fontana repository, be sure to include submodules:

```bash
git clone --recursive https://github.com/your-org/fontana.git
```

If you've already cloned without submodules, initialize them with:

```bash
git submodule update --init --recursive
```

### Building the Extension

To build the pylestia Rust extension:

```bash
cd src/fontana/core/da/pylestia
maturin develop --release
```

This will compile the Rust code and install the Python module in your current environment.

## Usage in Fontana

Fontana uses pylestia through the `CelestiaClient` class in `src/fontana/core/da/client.py`. This class handles:

- Connecting to Celestia nodes
- Posting blocks to the Celestia DA layer
- Retrieving blocks from the DA layer
- Managing namespace IDs

### Namespace Handling

One of the key aspects of the integration is proper namespace handling. Celestia requires namespaces to be valid 8-byte hex values. The `CelestiaClient` handles this through:

1. The `_namespace_id_bytes` method which converts namespace IDs to bytes
2. The `_get_namespace_for_block` method which generates deterministic namespace IDs for blocks

### Integration Tests

The integration is thoroughly tested in `tests/test_celestia_client.py`. The tests use a mocking strategy that:

1. Mocks the Celestia client API calls
2. Verifies that the correct parameters are passed to the API
3. Tests namespace handling and blob construction

## Troubleshooting

### Common Issues

1. **Import Errors**: If you see "No module named 'pylestia'", make sure you've built the extension with `maturin develop --release`.

2. **Type Errors**: The Rust extension expects specific types for parameters. Ensure namespace IDs are valid hex strings that can be properly converted to 8-byte arrays.

3. **Connection Issues**: Check your Celestia node URL and auth token configuration.

### Debugging

- Set the `RUST_LOG` environment variable to `debug` or `trace` for more verbose logging from the Rust extension.
- Use the `CelestiaClient` with `enabled=False` for testing without a real Celestia node.

## Upgrading Pylestia

To update the pylestia submodule to a newer version:

```bash
cd src/fontana/core/da/pylestia
git fetch
git checkout <target-tag-or-commit>
cd ../../../..
git add src/fontana/core/da/pylestia
git commit -m "Update pylestia to <version>"
```

Then rebuild the extension with `maturin develop --release`.
