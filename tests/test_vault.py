from fontana.core.models.vault import VaultDeposit
from fontana.core.models.vault import VaultWithdrawal
from fontana.core.models.utxo import UTXO


def test_withdrawal_with_full_utxos():
    utxos = [
        UTXO(txid="txa", output_index=0, recipient="font1user...", amount=2.0, status="spent"),
        UTXO(txid="txb", output_index=1, recipient="font1user...", amount=3.0, status="spent"),
    ]

    withdrawal = VaultWithdrawal(
        recipient_rollup_address="font1user...",
        recipient_celestia_address="celestia1dest...",
        vault_address="celestia1vault...",
        amount=5.0,
        timestamp=1713580000,
        related_utxos=utxos,
        tx_hash="txout777",
        processed_by="ops_team"
    )

    assert withdrawal.amount == 5.0
    assert withdrawal.related_utxos[0].txid == "txa"
    assert withdrawal.related_utxos[1].amount == 3.0
    assert withdrawal.id() == "txout777:font1user..."


def test_vault_deposit_basic():
    deposit = VaultDeposit(
        depositor_address="celestia1abcdef...",
        rollup_wallet_address="font1xyz...",
        vault_address="celestia1vault...",
        tx_hash="tx123456",
        amount=42.0,
        timestamp=1713569999,
        height=777,
        processed=False
    )

    assert deposit.depositor_address.startswith("celestia1")
    assert deposit.rollup_wallet_address.startswith("font1")
    assert deposit.amount == 42.0
    assert deposit.height == 777
    assert not deposit.processed


def test_vault_deposit_id_generation():
    deposit = VaultDeposit(
        depositor_address="celestia1abc...",
        rollup_wallet_address="font1recipient...",
        vault_address="celestia1vault...",
        tx_hash="tx789xyz",
        amount=3.14,
        timestamp=1713570000,
        height=999,
        processed=True
    )

    assert deposit.id() == "tx789xyz:font1recipient..."
