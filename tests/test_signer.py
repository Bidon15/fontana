from fontana.wallet.wallet import Wallet
from fontana.wallet.signer import Signer


def test_sign_and_verify_roundtrip():
    wallet = Wallet.generate()
    message = b"test message"
    signature = Signer.sign(message, wallet.signing_key.encode())
    assert Signer.verify(message, signature, wallet.verify_key.encode()) is True


def test_verify_fails_on_tampered_message():
    wallet = Wallet.generate()
    message = b"original"
    tampered = b"original but different"
    signature = Signer.sign(message, wallet.signing_key.encode())
    assert Signer.verify(tampered, signature, wallet.verify_key.encode()) is False


def test_verify_fails_on_wrong_key():
    wallet_1 = Wallet.generate()
    wallet_2 = Wallet.generate()
    message = b"important message"
    signature = Signer.sign(message, wallet_1.signing_key.encode())
    assert Signer.verify(message, signature, wallet_2.verify_key.encode()) is False