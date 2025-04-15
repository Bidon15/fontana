# 🛠 Fontana

**Fontana** is a simple, UTXO-based payment system designed for Python/Django developers.  
It enables devs to charge and pay per API call using TIA — no keys, no Stripe, no OAuth.

Just deploy, connect, and make money flow like a fontana.

---

## 📁 Project Structure

```
src/fontana/                  # Python package (created via `poetry new fontana`)
├── __init__.py

├── core/                 # UTXO ledger, transaction validation, Celestia batcher
│   └── __init__.py

├── wallet/               # SSH-style wallet CLI and key management
│   └── __init__.py

├── django_plugin/        # `@charge(tia=...)` decorator + Django middleware
│   └── __init__.py

├── sdk/                  # Python SDK for API consumers (e.g. `call_paid_api()`)
│   └── __init__.py

├── cli/                  # Typer CLI: init, topup, call, balance
│   └── __init__.py

├── scripts/              # Daemons (e.g. vault watcher, blob poster)
│   └── __init__.py

├── examples/             # Sample provider + consumer apps
│   └── summarize_api/

tests/                    # Unit + integration tests
├── test_wallet.py
```

---

## 🏁 Quickstart

```bash
# Install dependencies
poetry install

# Enter virtual environment
poetry shell
```

```bash
# CLI usage (to be implemented)
fontana init                # Create SSH-style wallet
fontana topup 10            # Load TIA from vault
fontana-call \
  --to https://api.example.com/summary \
  --input input.json \
  --max-price 0.01
```

---

## 🎯 Core Goals

- One-line monetization for Django APIs: `@charge(tia=...)`
- SSH-style keys instead of seed phrases
- Pay-per-request using real UTXOs (no auth tokens)
- API composability by default
- Celestia used as the data availability & recovery layer

---

## 🤝 Team

Built in Berlin and Odesa.  
Inspired by Odesa's Fontana district — where things flow with chill vibes.
