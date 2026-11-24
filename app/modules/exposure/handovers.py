from .probes import *  # noqa: F401,F403
from .probes import (  # noqa: F401
    ProbeContext, active_reading, build_context, context,
    handovers, load_handovers, normalize_handovers, parse_handovers,
    probe_context, read_handovers, resolve_reading, select, select_reading,
)


def normalize(records):
    return build_context(records)


def apply(temperature_rows, records=None):
    from .temperature import normalize as normalize_temperatures
    context = records if isinstance(records, ProbeContext) else build_context(records)
    return normalize_temperatures(temperature_rows, context)


def resolve_at(door, point, temperature_history, records=None):
    context = records if isinstance(records, ProbeContext) else build_context(records)
    return select_reading(door, point, temperature_history, context)


def resolve(*args, **kwargs):
    return select_reading(*args, **kwargs)
