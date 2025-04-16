from fontana.core.models.transaction import SignedTransaction
from fontana.core.models.utxo import UTXO, UTXORef


def test_transaction_input_output_keys():
    tx = SignedTransaction(
        txid="abc123",
        sender_address="font1userxyz...",
        inputs=[
            UTXORef(txid="prevtx1", index=0),
            UTXORef(txid="prevtx2", index=1)
        ],
        outputs=[
            UTXO(txid="abc123", index=0, recipient="font1provider...", amount=0.65, status="unspent"),
            UTXO(txid="abc123", index=1, recipient="font1fontana...", amount=0.35, status="unspent")
        ],
        fee=0.05,
        payload_hash="fakehash123",
        timestamp=1713552000,
        signature="fakesig456"
    )

    assert tx.input_keys() == ["prevtx1:0", "prevtx2:1"]
    assert tx.output_keys() == ["abc123:0", "abc123:1"]
    assert tx.fee == 0.05
    assert tx.sender_address.startswith("font1")
