from fontana.wallet import Wallet
import os

def test_wallet_generate_and_save(tmp_path):
    wallet = Wallet.generate()
    path = tmp_path / "wallet.json"
    wallet.save(str(path))
    
    loaded = Wallet.load(str(path))
    assert loaded.get_address() == wallet.get_address()