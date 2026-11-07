"""Standard text rates, verified 2026-11-05.
Source: https://developers.openai.com/api/docs/models/gpt-4o-mini
Integer nanodollars preserve sub-cent costs exactly. One USD = 1,000,000,000.
Unknown models/tiers are unpriced, never silently treated as free.
"""
from decimal import Decimal

VERSION = 'openai-standard-2026-11-05'
# Input, cached input, output: $0.15 / $0.075 / $0.60 per million tokens.
RATES = {'gpt-4o-mini': (150, 75, 600), 'gpt-4o-mini-2024-07-18': (150, 75, 600)}

def usd(nano):
    return str(Decimal(nano) / Decimal(1_000_000_000)) if nano is not None else None

def estimate(response):
    usage = response.usage
    counts = [getattr(usage, 'prompt_tokens', None), getattr(usage, 'completion_tokens', None)]
    details = getattr(usage, 'prompt_tokens_details', None)
    cached = getattr(details, 'cached_tokens', 0) if details is not None else 0
    result = dict(input_tokens=None, output_tokens=None, cached_tokens=None, cost_nano_usd=None,
                  input_rate=None, cached_rate=None, output_rate=None, pricing_version=None, reason=None)
    if not all(type(n) is int and n >= 0 for n in [*counts, cached]) or cached > counts[0] or sum(counts) != usage.total_tokens:
        result['reason'] = 'Token breakdown unavailable or inconsistent'
        return result
    result.update(input_tokens=counts[0], output_tokens=counts[1], cached_tokens=cached)
    model = getattr(response, 'model', None)
    rates = RATES.get(model) if isinstance(model, str) else None
    if rates is None:
        result['reason'] = 'Model price unavailable'
        return result
    if getattr(response, 'service_tier', None) not in (None, 'default', 'standard'):
        result['reason'] = 'Service tier price unavailable'
        return result
    inp, cache, out = rates
    result.update(input_rate=inp, cached_rate=cache, output_rate=out, pricing_version=VERSION,
                  cost_nano_usd=(counts[0]-cached)*inp + cached*cache + counts[1]*out)
    return result
