"""
Verify that the trade-completion callback registry in trade_executor works correctly.

Usage:
    python3 verify_callbacks.py
    # or inside the container:
    docker compose run --rm arbitrage-dashboard python verify_callbacks.py
"""

import contextlib
import io

from triangular_arbitrage.trade_executor import (
    _fire_trade_callbacks,
    register_trade_callback,
)


def dummy_callback():
    print("CALLBACK FIRED")


# Register the dummy callback
register_trade_callback(dummy_callback)

# Capture stdout while firing
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    _fire_trade_callbacks()

output = buf.getvalue()
assert "CALLBACK FIRED" in output, (
    f"Expected 'CALLBACK FIRED' in captured output, got: {repr(output)}"
)

print("✓ register_trade_callback: OK")
print("✓ _fire_trade_callbacks:   OK")
print("✓ Callback wiring verified successfully")
