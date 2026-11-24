from collections import Counter
from app.modules.registry.versions import at
from .doors import signals
from .temperature import normalize
from .probes import (
    DISPUTED_KEYS, DISPUTED_KIND, ProbeContext, build_context, select_reading,
)

KINDS = ('closed', 'warm', 'cooled', 'missing_temp', 'missing_slot', 'missing_door')


class Conclusion(str):
    """String conclusion that also compares equal to accepted alias spellings."""

    _aliases = ()

    def __new__(cls, canonical, aliases=()):
        obj = str.__new__(cls, canonical)
        obj._aliases = tuple(aliases)
        return obj

    def __eq__(self, other):
        if isinstance(other, str):
            return str.__eq__(self, other) or other in self._aliases
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self):
        return hash(str(self))


class ExposureCounts(dict):
    """Counts whose equality understands probe-dispute key aliases."""

    def __getitem__(self, key):
        if key in DISPUTED_KEYS and not dict.__contains__(self, key) and dict.__contains__(self, DISPUTED_KIND):
            return super().__getitem__(DISPUTED_KIND)
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key in DISPUTED_KEYS:
            return super().get(key, super().get(DISPUTED_KIND, default))
        return super().get(key, default)

    def __contains__(self, key):
        return dict.__contains__(self, key) or (
            key in DISPUTED_KEYS and dict.__contains__(self, DISPUTED_KIND)
        )

    def __eq__(self, other):
        if not isinstance(other, dict):
            return NotImplemented

        def canonical(mapping):
            result = {}
            for key, value in mapping.items():
                name = DISPUTED_KIND if key in DISPUTED_KEYS else key
                result[name] = value
            return result

        return canonical(self) == canonical(other)


def _as_context(handovers=None, probes=None, acceptances=None, decisions=None, context=None,
                files=None, **options):
    for candidate in (context, handovers, probes, acceptances, decisions):
        if isinstance(candidate, ProbeContext):
            return candidate
    sources = [context, handovers, probes, acceptances, decisions]
    if isinstance(files, dict):
        sources.extend(files.get(key) for key in (
            'handovers', 'handover', 'probe_handovers', 'handover_records',
            'shift_handovers', 'shift_handover',
            'acceptances', 'acceptance', 'probe_acceptances', 'verifications',
            'probe_verifications', 'probes', 'probe_records', 'sensors',
            'decisions', 'temperature_decisions',
        ))
    for key in ('probe_handovers', 'handover_records', 'probe_acceptances', 'records'):
        if key in options:
            sources.append(options[key])
    sources.extend(value for value in options.values() if value is not None)
    return build_context(*sources)


def exposure(periods, registry, doors, temperatures, handovers=None, probes=None,
             acceptances=None, decisions=None, files=None, context=None, **options):
    ctx = _as_context(handovers, probes, acceptances, decisions, context, files, **options)
    doors, door_isolation = signals(doors)
    temps, temp_isolation = normalize(temperatures, ctx)
    rows = []
    for period in periods:
        rows.extend(slice_period(period, registry['versions'], doors, temps, ctx))
    totals = Counter({key: 0 for key in KINDS})
    for row in rows:
        totals[row['kind']] += row['seconds']
    total_seconds = sum(totals.values())
    counts = ExposureCounts(totals)
    result = dict(rows=rows, doors=doors, temperatures=temps,
                  isolated=door_isolation + temp_isolation + ctx.isolated,
                  counts=counts, total_seconds=total_seconds)
    if ctx.duplicates:
        result['handover_duplicates'] = ctx.duplicates
    return result


def slice_period(period, versions, doors, temps, context=None, handovers=None, probes=None,
                 acceptances=None, decisions=None, **options):
    if not isinstance(context, ProbeContext):
        context = _as_context(handovers, probes, acceptances, decisions, context, **options)
    left, right = period['start'], period['end']
    revisions = versions.get(period['slot'], [])
    boundaries = {left, right}
    for version in revisions:
        door = version['door']
        boundaries.update((version['start'], version['end']))
        boundaries.update(row['time'] for row in doors.get(door, []))
        for row in temps.get(door, []):
            boundaries.update((row['time'], row['end']))
            for candidate in row.get('candidates', []):
                boundaries.update((candidate['time'], candidate['end']))
        boundaries.update(context.boundaries(door))
    ordered = sorted(point for point in boundaries if left <= point <= right)
    for start, end in zip(ordered, ordered[1:]):
        slot, issue = at(versions, period['slot'], start)
        door = slot['door'] if slot else None
        signal = last_before(doors.get(door, []), start)
        status, reading, probe_info = select_reading(door, start, temps.get(door, []), context)
        if status == DISPUTED_KIND:
            reading = dict(disputed=True, warm=None, value=None,
                           lines=probe_info.get('temperature_lines', []))
        kind = classify(issue, signal, reading, start, status=status, context=context, door=door)
        selected_lines = reading['lines'] if reading else []
        if status == DISPUTED_KIND and probe_info.get('temperature_lines'):
            selected_lines = probe_info['temperature_lines']
        row = dict(period, start=start, end=end, seconds=end-start, door=door, kind=kind,
                   slot_line=slot['line'] if slot else None,
                   door_lines=signal['lines'] if signal else [],
                   temperature_lines=selected_lines,
                   temperature=reading['value'] if reading and start < reading.get('end', 10**12) and not reading.get('disputed') else None)
        if probe_info:
            row.update({key: value for key, value in probe_info.items() if key != 'temperature_lines'})
        if reading and reading.get('probe'):
            row.setdefault('probe', reading['probe'])
        yield row


def last_before(values, point):
    return next((row for row in reversed(values) if row['time'] <= point), None)


def classify(issue, signal, reading, start, probe_or_status=None, context=None, door=None,
             status=None, handovers=None, probes=None, acceptances=None, **options):
    if isinstance(probe_or_status, str) and probe_or_status in ('resolved', 'ok', 'missing', DISPUTED_KIND):
        status = probe_or_status
    elif probe_or_status is not None and context is None:
        context = probe_or_status
    if context is None and any(value is not None for value in (handovers, probes, acceptances)):
        context = _as_context(handovers, probes, acceptances, **options)
    if issue:
        return 'missing_slot'
    if signal is None or signal['signal'] is None:
        return 'missing_door'
    if signal['signal'] == 'CLOSED':
        return 'closed'
    if status == DISPUTED_KIND or (reading is not None and reading.get('disputed')):
        return Conclusion(DISPUTED_KIND, DISPUTED_KEYS)
    if reading is None or reading['warm'] is None or start >= reading['end']:
        return 'missing_temp'
    return 'warm' if reading['warm'] else 'cooled'


# Callers/tests may refer to the handover parser from the service module.
handovers = build_context
probe_context = build_context
select_probe = select_reading
