import typer
from fontana.wallet.wallet import Wallet
import os

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

@app.command()
def show():
    """Show your public wallet address."""
    wallet = Wallet.load(DEFAULT_PATH)
    typer.echo(f"👛 Address: {wallet.get_address()}")

@app.command()
def topup(amount: float):
    """Mock top-up command to simulate loading TIA into your rollup balance."""
    typer.echo(f"💰 You have 'topped up' {amount} TIA (mock). Real funds will be detected via vault watcher.")

@app.command()
def call(endpoint: str, input: str, max_price: float = typer.Option(0.01, help="Maximum TIA you're willing to pay")):
    """Mock API call to another Fontana-compliant endpoint."""
    typer.echo(f"🔗 Calling {endpoint} with input: {input}")
    typer.echo(f"💸 Paying up to {max_price} TIA for this call (mock)")
    typer.echo("✅ API call simulated (no real network requests yet)")

@app.command("help")
def help_command():
    """Show all available commands and usage."""
    typer.echo("""
    Fontana CLI – Pay-per-call UTXO API rollup

    Available commands:

    init               Create a new wallet at ~/.fontana/wallet.json
    show               Display your public wallet address
    topup [amount]     Mock top-up to simulate TIA balance
    call               Mock paid API call using rollup logic
    help               Show this help message

    Examples:

    fontana init
    fontana show
    fontana topup 10
    fontana call --endpoint https://api.foo.dev/summarize --input input.json --max-price 0.02
    """)

if __name__ == "__main__":
    app()
