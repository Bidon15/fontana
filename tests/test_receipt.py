import json
from fontana.core.models.receipt import ReceiptProof
from fontana.core.models.transaction import SignedTransaction
from fontana.core.models.block import BlockHeader
from fontana.core.models.utxo import UTXO, UTXORef


def make_dummy_tx(txid="tx123") -> SignedTransaction:
    return SignedTransaction(
        txid=txid,
        sender_address="font1alice...",
        inputs=[UTXORef(txid="prevtx", index=0)],
        outputs=[
            UTXO(txid=txid, index=0, recipient="font1provider...", amount=0.5, status="unspent")
        ],
        fee=0.01,
        payload_hash="hash123",
        timestamp=1713581111,
        signature="sigABC"
    )


def make_dummy_block_header() -> BlockHeader:
    return BlockHeader(
        height=69,
        prev_hash="abc123",
        state_root="root456",
        timestamp=1713581122,
        tx_count=1,
        blob_ref="blob789",
        fee_schedule_id="v1"
    )


def test_receipt_generation():
    tx = make_dummy_tx()
    header = make_dummy_block_header()

    receipt = ReceiptProof(
        tx=tx,
        block_header=header,
        index=0,
        included_at=1713581133,
        provider_url="https://api.example.com/summarize"
    )

    sql_row = receipt.to_sql_row()

    assert receipt.id() == "tx123:0"
    assert sql_row["receipt_id"] == "tx123:0"
    assert sql_row["block_height"] == 69
    assert "full_json" in sql_row
    assert "provider" in sql_row and sql_row["provider"].startswith("font1")
