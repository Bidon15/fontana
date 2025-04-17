from fontana.core.models.utxo import UTXO, UTXORef


def test_utxo_ref_to_key():
    ref = UTXORef(txid="abc123", output_index=0)
    assert ref.to_key() == "abc123:0"


def test_utxo_lifecycle():
    utxo = UTXO(
        txid="tx789",
        output_index=1,
        recipient="font1xyz...",
        amount=1.5,
        status="unspent"
    )

    assert utxo.key() == "tx789:1"
    assert not utxo.is_spent()

    utxo.status = "spent"
    assert utxo.is_spent()
