import os
import json
import base64
from nacl import signing
from nacl.encoding import Base64Encoder

DEFAULT_WALLET_PATH = os.path.expanduser("~/.fontana/wallet.json")


class Wallet:
    def __init__(self, signing_key: signing.SigningKey):
        self.signing_key = signing_key
        self.verify_key = signing_key.verify_key

    @classmethod
    def generate(cls) -> "Wallet":
        key = signing.SigningKey.generate()
        return cls(key)

    @classmethod
    def load(cls, path: str = DEFAULT_WALLET_PATH) -> "Wallet":
        with open(path, "r") as f:
            data = json.load(f)
        key_bytes = base64.b64decode(data["private_key"])
        return cls(signing.SigningKey(key_bytes))

    def save(self, path: str = DEFAULT_WALLET_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({
                "private_key": base64.b64encode(self.signing_key.encode()).decode("utf-8")
            }, f)

    def get_address(self) -> str:
        return self.verify_key.encode(encoder=Base64Encoder).decode("utf-8")
