import typer
from fontana.wallet.wallet import Wallet
import os
from fontana.cli import wallet as wallet_commands

app = typer.Typer()
DEFAULT_PATH = os.path.expanduser("~/.fontana/wallet.json")


@app.command()
def init():
    """Generate a new wallet and save it locally."""
    if os.path.exists(DEFAULT_PATH):
        typer.echo("⚠️  Wallet already exists at ~/.fontana/wallet.json")
        raise typer.Exit()

    wallet = Wallet.generate()
    wallet.save(DEFAULT_PATH)
    typer.echo("✅ Wallet created and saved to ~/.fontana/wallet.json")


# show command has been moved to wallet.py as 'address'


@app.command()
def topup(amount: float):
    """Mock top-up command to simulate loading TIA into your rollup balance."""
    typer.echo(
        f"💰 You have 'topped up' {amount} TIA (mock). Real funds will be detected via vault watcher."
    )


@app.command()
def call(
    endpoint: str,
    input: str,
    max_price: float = typer.Option(0.01, help="Maximum TIA you're willing to pay"),
):
    """Mock API call to another Fontana-compliant endpoint."""
    typer.echo(f"🔗 Calling {endpoint} with input: {input}")
    typer.echo(f"💸 Paying up to {max_price} TIA for this call (mock)")
    typer.echo("✅ API call simulated (no real network requests yet)")


@app.command("help")
def help_command():
    """Show all available commands and usage."""
    typer.echo(
        """
    Fontana CLI – Pay-per-call UTXO API rollup

    Available commands:

    init               Create a new wallet at ~/.fontana/wallet.json
    topup [amount]     Mock top-up to simulate TIA balance
    call               Mock paid API call using rollup logic
    help               Show this help message

    wallet             Real wallet operations with the UTXO ledger:
      create           Create a new wallet with optional name
      balance          Check your real balance on the ledger
      send             Send a transaction to another address
      list-utxos       List all UTXOs owned by your wallet

    Examples:

    fontana init
    fontana wallet address                                        # Show default wallet address
    fontana wallet address --name alice                          # Show alice's wallet address
    fontana wallet create --name alice                           # Create new wallet for alice
    fontana wallet create --path "/path/to/custom/wallet.json"   # Create wallet at custom path
    fontana wallet balance --name alice                          # Check alice's balance
    fontana wallet balance --path "/path/to/custom/wallet.json" # Check custom wallet balance
    fontana wallet send --to <ADDRESS> --amount 10.0             # Send from default wallet
    fontana wallet send --from-wallet alice --to <ADDRESS> --amount 5.0
    fontana wallet send --path "/path/to/custom/wallet.json" --to <ADDRESS> --amount 5.0
    fontana wallet list-utxos --name alice                       # List alice's UTXOs
    fontana call --endpoint https://api.foo.dev/summarize --input input.json --max-price 0.02
    """
    )


# Add wallet commands to main CLI
app.add_typer(
    wallet_commands.wallet_app,
    name="wallet",
    help="Real wallet operations using the UTXO ledger",
)

if __name__ == "__main__":
    app()
