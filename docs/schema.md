# Fontana Schema Diagram

Below is a high-level Mermaid diagram illustrating the relationships between the core SQLite tables in Fontana.

```mermaid
flowchart LR
  subgraph "Vault Flow"
    VD["Vault Deposits
(tx_hash, rollup_wallet_address)"] --> U[UTXOs]
  end

  subgraph "API Calls"
    U --> TX[Transactions]
    TX --> B[Blocks]
    B --> R[Receipts]
  end

  subgraph "Withdrawal Flow"
    U --> VW[Vault Withdrawals]
  end

  %% Define table details
  VD -- "deposits" --> U
  U -- "inputs/outputs" --> TX
  TX -- "batched into" --> B
  B -- "generates" --> R
  U -- "burned by" --> VW

  style VD fill:#f9f,stroke:#333,stroke-width:1px
  style U  fill:#ff9,stroke:#333,stroke-width:1px
  style TX fill:#9ff,stroke:#333,stroke-width:1px
  style B  fill:#9f9,stroke:#333,stroke-width:1px
  style R  fill:#f99,stroke:#333,stroke-width:1px
  style VW fill:#99f,stroke:#333,stroke-width:1px
```

**Table relationships:**

- **Vault Deposits** → mint new **UTXOs**
- **UTXOs** → consumed and created by **Transactions**
- **Transactions** → grouped into **Blocks**
- **Blocks** → referenced by **Receipts** (proofs)
- **UTXOs** → burned when fulfilling **Vault Withdrawals**
