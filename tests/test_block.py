import random
import string
from fontana.core.models.transaction import SignedTransaction
from fontana.core.models.utxo import UTXO, UTXORef
from fontana.core.models.block import Block, BlockHeader


def make_dummy_tx() -> SignedTransaction:
    rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    txid = f"tx_{rand}"
    input_txid = f"input_{rand}"

    return SignedTransaction(
        txid=txid,
        sender_address="font1alice...",
        inputs=[UTXORef(txid=input_txid, index=0)],
        outputs=[UTXO(txid=txid, index=0, recipient="font1bob...", amount=1.0, status="unspent")],
        fee=0.01,
        payload_hash="payload123",
        timestamp=1713560000,
        signature=f"sig_{rand}"
    )

def test_block_with_transactions():
    tx1 = make_dummy_tx()
    tx2 = make_dummy_tx()

    header = BlockHeader(
        height=7,
        prev_hash="prev000",
        state_root="root777",
        timestamp=1713560500,
        tx_count=2,
        blob_ref="blob456",
        fee_schedule_id="v2"
    )

    block = Block(header=header, transactions=[tx1, tx2])

    assert block.header.height == 7
    assert len(block.transactions) == 2
    assert tx1.txid != tx2.txid
    assert tx1.inputs[0].txid != tx2.inputs[0].txid
