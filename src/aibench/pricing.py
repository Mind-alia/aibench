"""Turn tokens into dollars when a tool does not say what a run cost, from the prices you wrote in pricing.toml."""

from __future__ import annotations

from pathlib import Path

from .adapters import Usage
from .model import read_toml


def load_prices(path: Path | None) -> dict[str, dict[str, float]]:
    if path is None or not path.is_file():
        return {}
    return {str(name): {k: float(v) for k, v in values.items()}
            for name, values in (read_toml(path).get("models") or {}).items()}


def apply(usage: Usage, model: str, prices: dict[str, dict[str, float]]) -> Usage:
    """Fill cost_usd from prices when the tool gave none; leave it unknown when the model has no price."""
    if usage.cost_usd is not None or model not in prices:
        return usage
    price = prices[model]
    fresh = max(usage.input_tokens - usage.cache_read_tokens, 0)
    cost = (fresh * price.get("input", 0.0) + usage.cache_read_tokens * price.get("cached_input", price.get("input", 0.0))
            + usage.output_tokens * price.get("output", 0.0)) / 1_000_000
    usage.cost_usd, usage.cost_source = round(cost, 6), "priced"
    return usage
