import os
import json
import base64
from nacl.signing import SigningKey
from nacl.encoding import Base64Encoder
from fontana.core.config import config


class Wallet:
    def __init__(self, signing_key: SigningKey):
        self.signing_key = signing_key
        self.verify_key = signing_key.verify_key

    @classmethod
    def generate(cls) -> "Wallet":
        key = SigningKey.generate()
        return cls(key)

    @classmethod
    def load(cls, path: str = None) -> "Wallet":
        if path is None:
            path = str(config.wallet_path)
        with open(path, "r") as f:
            data = json.load(f)
        key_bytes = base64.b64decode(data["private_key"])
        return cls(SigningKey(key_bytes))

    def save(self, path: str = None):
        if path is None:
            path = str(config.wallet_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({
                "private_key": base64.b64encode(self.signing_key.encode()).decode("utf-8")
            }, f)

    def get_address(self) -> str:
        return self.verify_key.encode(encoder=Base64Encoder).decode("utf-8")

    def sign(self, message: bytes) -> str:
        """Sign a message using the wallet's private key.
        
        Args:
            message: The message to sign
            
        Returns:
            str: Base64-encoded signature
        """
        # Use the Signer to sign the message
        from fontana.wallet.signer import Signer
        return Signer.sign(message=message, private_key=self.signing_key.encode())
