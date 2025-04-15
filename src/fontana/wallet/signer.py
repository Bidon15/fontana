from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import Base64Encoder
import base64


class Signer:
    @staticmethod
    def sign(message: bytes, private_key: bytes) -> str:
        # The private_key is already encoded from Wallet.signing_key.encode()
        key = SigningKey(private_key)
        signed = key.sign(message)
        return base64.b64encode(signed.signature).decode("utf-8")

    @staticmethod
    def verify(message: bytes, signature: str, public_key: bytes) -> bool:
        # The public_key is already encoded from Wallet.verify_key.encode()
        key = VerifyKey(public_key)
        try:
            key.verify(message, base64.b64decode(signature))
            return True
        except Exception:
            return False
