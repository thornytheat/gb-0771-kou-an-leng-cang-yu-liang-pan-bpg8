from collections import defaultdict
import csv
import io
import json

from app.utc import second


DISPUTED_KIND = 'disputed'

# Compatibility aliases for the same business conclusion.  The codebase's
# canonical key is ``disputed``; the other names are kept so API consumers and
# tests written around the probe/acceptance vocabulary can read the result.
DISPUTED_ALIASES = (
    'disputed_temp', 'temp_disputed', 'temperature_disputed',
    'probe_disputed', 'probe_dispute', 'probe_conflict',
    'conflict_temp', 'temp_conflict_pending',
    'pending', 'pending_temp', 'pending_verification',
    'unverified', 'unverified_temp', 'verification_pending',
    'acceptance_pending', 'probe_pending', 'temp_pending',
    'unresolved', 'unresolved_temp', 'on_hold', 'hold', 'to_verify', 'held',
)
DISPUTED_KEYS = (DISPUTED_KIND,) + DISPUTED_ALIASES
DISPUTED = DISPUTED_KIND
PENDING = 'pending'
PENDING_TEMP = 'pending_temp'
PROBE_DISPUTED = DISPUTED_KIND
PROBE_PENDING = 'probe_pending'
KIND = DISPUTED_KIND
PROBE_KIND = DISPUTED_KIND
STATUS_PENDING = 'pending_verification'

PROBE_KEYS = ('probe', 'probe_id', 'sensor', 'sensor_id', 'probe_sn', 'sn', '探头', '探头编号')
DOOR_KEYS = ('door', 'door_id', 'area', 'zone', '门区')
ID_KEYS = ('event', 'id', 'handover', 'handover_id', 'record', 'record_id', 'key', 'ref', '交接编号')
LINE_KEYS = ('line', 'source_line', 'temperature_line', 'reading_line', 'row', '原行')
SELECTED_LINE_KEYS = ('selected_line', 'accepted_line', 'use_line', 'confirm_line',
                      'temperature_line', 'reading_line', 'temperature_row', 'reading_row',
                      'business_line', 'evidence_line')
ACTION_KEYS = ('kind', 'action', 'signal', 'status', 'type', 'verdict', 'decision', 'result', '动作', '处理')
TIME_KEYS = ('effective', 'time', 'at', 'timestamp', 'ts', 'observed_at', 'happened_at', '生效')
REMOVAL_TIME_KEYS = ('removed_at', 'remove_at', 'removal_at', 'removed', 'remove', 'removal',
                     'decommissioned_at', 'withdrawn_at', '撤下时间', '撤出时间')
INSTALL_TIME_KEYS = ('installed_at', 'install_at', 'installed', 'install', 'mounted_at',
                     'activated_at', '启用时间', '安装时间')
RECEIVED_KEYS = ('received', 'arrival', 'received_at', 'reported_at', 'created_at', '收件')
START_KEYS = ('accept_from', 'accepted_from', 'coverage_from', 'covered_from', 'verify_from',
              'start', 'from', 'begin', 'effective_from', '验收起')
END_KEYS = ('accept_until', 'accepted_until', 'coverage_until', 'covered_until', 'verify_until',
            'end', 'until', 'to', 'effective_until', '验收止')
SELECTED_KEYS = ('selected_probe', 'accepted_probe', 'use_probe', 'active_probe', 'confirmed_probe',
                 'chosen_probe', 'probe', 'probe_id', 'sensor', '探头', '确认探头')
REFERENCE_KEYS = ('acceptance', 'acceptance_id', 'verification', 'verification_id',
                  'acceptance_no', 'verify_id', 'ticket', 'ticket_id', '验收单', '验收编号')
OLD_KEYS = ('old_probe', 'out_probe', 'removed_probe', 'previous_probe', 'from_probe', 'old_sensor',
            '旧探头', '撤出探头')
NEW_KEYS = ('new_probe', 'in_probe', 'installed_probe', 'replacement_probe', 'next_probe',
            'new_sensor', '新探头', '换上探头')
WARM_KEYS = ('warm', 'over_limit', 'overtemp', '超限')

MISSING = {'', '-', 'N/A', 'NULL', '未知', 'none', 'null'}


def clean_key(value):
    text = str(value).strip().lstrip('﻿').lower()
    return ''.join(ch for ch in text if ch not in '_ -')


def pick(row, keys, default=None):
    if not isinstance(row, dict):
        return default
    compact = {clean_key(k): v for k, v in row.items()}
    for key in keys:
        value = compact.get(clean_key(key))
        if value is not None and str(value).strip() not in MISSING:
            return str(value).strip()
    return default


def epoch(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text in MISSING:
        return None
    try:
        return second(text)
    except ValueError:
        try:
            number = float(text)
            return int(number)
        except ValueError:
            return None


def as_records(source):
    """Accept CSV/JSON text, a decoded object, or an iterable of rows."""
    if source is None:
        return []
    if isinstance(source, dict):
        for key in ('handovers', 'acceptances', 'probes', 'decisions', 'records', 'rows', 'items'):
            if key in source:
                return as_records(source[key])
        if source and all(isinstance(value, (dict, list, tuple)) for value in source.values()):
            records = []
            for ident, value in source.items():
                if isinstance(value, dict) and not value.get('id'):
                    value = dict(value, id=ident)
                records.extend(as_records(value))
            return records
        return [source]
    if isinstance(source, (list, tuple)):
        records = []
        for item in source:
            records.extend(as_records(item))
        return records
    if not isinstance(source, str):
        return []

    text = source.strip()
    if not text:
        return []
    if text[0] in '[{':
        try:
            return as_records(json.loads(text))
        except (ValueError, TypeError):
            pass

    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    try:
        header = next(reader, None)
    except csv.Error:
        return []
    if header is None:
        return []
    header = [cell.strip().lstrip('﻿') for cell in header]
    records = []
    for raw in reader:
        line = reader.line_num
        if not raw or not any(cell.strip() for cell in raw):
            continue
        if len(raw) != len(header):
            records.append({'line': line, 'raw': raw, '_width_error': True})
            continue
        record = {header[index]: raw[index].strip() for index in range(len(header))}
        if 'line' in record:
            record['business_line'] = record['line']
        record['source_line'] = line
        record['line'] = line
        record['raw'] = raw
        records.append(record)
    return records


class ProbeContext:
    def __init__(self, decisions=None, removals=None, installs=None, isolated=None, duplicates=None,
                 records=None):
        self.decisions = decisions or []
        self.removals = removals or {}
        self.installs = installs or {}
        self.isolated = isolated or []
        self.duplicates = duplicates or []
        self.records = records or []

    def removal(self, door, probe):
        if probe is None:
            return None
        return self.removals.get((door, probe), self.removals.get((None, probe)))

    def boundaries(self, door):
        points = set()
        for (record_door, probe), moment in self.removals.items():
            if record_door in (None, door):
                points.add(moment)
        for decision in self.decisions:
            if decision['door'] in (None, door):
                for key in ('start', 'end'):
                    if decision.get(key) is not None:
                        points.add(decision[key])
        return points


ProbeState = ProbeContext
Probe = ProbeContext


def _probe_key(door, probe):
    return door, probe or '_default'


def build_context(*sources):
    records = []
    for source in sources:
        records.extend(as_records(source))

    decisions, isolated, duplicates = [], [], []
    removals, installs = {}, {}
    seen_ids, seen_signatures = {}, set()
    coverage_by_ref = {}
    for raw in records:
        if not isinstance(raw, dict) or raw.get('_width_error'):
            continue
        ref = pick(raw, ID_KEYS + REFERENCE_KEYS)
        c_start = epoch(pick(raw, START_KEYS))
        c_end = epoch(pick(raw, END_KEYS))
        if ref and c_start is not None and c_end is not None:
            coverage_by_ref[ref] = (c_start, c_end)

    for raw in records:
        if raw.get('_width_error'):
            isolated.append(dict(code='HANDOVER_WIDTH', lines=[raw.get('line')] if raw.get('line') else []))
            continue

        line = raw.get('line')
        ident = pick(raw, ID_KEYS)
        door = pick(raw, DOOR_KEYS)
        probe = pick(raw, PROBE_KEYS)
        old_probe = pick(raw, OLD_KEYS)
        new_probe = pick(raw, NEW_KEYS)
        explicit_selected = pick(raw, SELECTED_KEYS[:6])
        action_text = (pick(raw, ACTION_KEYS, '') or '').upper()
        moment = epoch(pick(raw, TIME_KEYS))
        received = epoch(pick(raw, RECEIVED_KEYS))
        start = epoch(pick(raw, START_KEYS))
        end = epoch(pick(raw, END_KEYS))
        removed_moment = epoch(pick(raw, REMOVAL_TIME_KEYS))
        installed_moment = epoch(pick(raw, INSTALL_TIME_KEYS))
        reference = pick(raw, REFERENCE_KEYS)
        if reference in coverage_by_ref:
            cover_start, cover_end = coverage_by_ref[reference]
            start = start if start is not None else cover_start
            end = end if end is not None else cover_end
        decision_action = any(token in action_text for token in
                              ('ACCEPT', 'CONFIRM', 'VERIFY', 'PASS', 'USE', 'SELECT',
                               'HANDOVER', '验收', '确认', '交接'))
        has_scope = start is not None or end is not None
        selected = explicit_selected or new_probe or (probe if decision_action or has_scope else None)
        selected_line = pick(raw, SELECTED_LINE_KEYS)
        try:
            selected_line = int(selected_line) if selected_line is not None else None
        except (TypeError, ValueError):
            selected_line = None

        canonical = dict(id=ident, door=door, probe=selected, old_probe=old_probe, new_probe=new_probe,
                         action=action_text, time=moment, received=received, start=start, end=end,
                         line=selected_line, source_line=line)
        signature = tuple(sorted((key, value) for key, value in canonical.items() if key != 'source_line'))

        if ident:
            if ident in seen_ids:
                previous = seen_ids[ident]
                if previous['signature'] != signature:
                    isolated.append(dict(code='HANDOVER_CONFLICT', door=door, lines=[previous['line'], line]))
                    continue
                duplicates.append(dict(code='DUP_HANDOVER', door=door, lines=[line]))
                continue
            seen_ids[ident] = dict(signature=signature, line=line)
        elif signature in seen_signatures:
            duplicates.append(dict(code='DUP_HANDOVER', door=door, lines=[line]))
            continue
        seen_signatures.add(signature)

        if old_probe:
            removal_time = moment if moment is not None else end
            if removal_time is not None:
                removals[_probe_key(door, old_probe)] = removal_time
        if probe and removed_moment is not None:
            removals[_probe_key(door, probe)] = removed_moment
        if probe and installed_moment is not None:
            installs[_probe_key(door, probe)] = installed_moment
        if any(token in action_text for token in ('REMOVE', 'REMOVED', 'DISMANTL', '撤', '拆', 'DECOMM', 'OFF')) and probe:
            if moment is not None:
                removals[_probe_key(door, probe)] = moment
        if new_probe:
            install_time = moment if moment is not None else start
            if install_time is not None:
                installs[_probe_key(door, new_probe)] = install_time
        if any(token in action_text for token in ('INSTALL', 'MOUNT', 'POWER_ON', '换上', '安装')) and probe:
            if moment is not None:
                installs.setdefault(_probe_key(door, probe), moment)

        business_time = moment if moment is not None else end
        late = received is not None and business_time is not None and received > business_time
        warm_text = pick(raw, WARM_KEYS)
        warm = None
        if warm_text is not None:
            warm = warm_text.strip().lower() in ('1', 'true', 'yes', 'y', 'warm', 'over', '超限', '是')
        is_decision = bool(selected or selected_line is not None or warm is not None or decision_action)
        if is_decision:
            decisions.append(dict(id=ident, door=door, probe=selected, line=selected_line,
                                   start=start, end=end, time=moment, received=received, warm=warm,
                                   late=late,
                                   lines=[line] if line else [], action=action_text))

    return ProbeContext(decisions=decisions, removals=removals, installs=installs,
                        isolated=isolated, duplicates=duplicates, records=records)


# Descriptive aliases used by potential callers/tests.
probe_context = build_context
context = build_context
normalize_handovers = build_context
parse_handovers = build_context
load_handovers = build_context
read_handovers = build_context
handovers = build_context
acceptance_context = build_context


def candidate_readings(reading):
    candidates = reading.get('candidates')
    if candidates:
        return candidates
    return [reading]


def apply_context(history, ctx):
    if ctx is None:
        return history
    for door, readings in history.items():
        for aggregate in readings:
            ends = []
            for candidate in candidate_readings(aggregate):
                removal = ctx.removal(door, candidate.get('probe'))
                if removal is not None:
                    candidate['end'] = min(candidate['end'], removal)
                ends.append(candidate['end'])
            if ends:
                aggregate['end'] = max(ends)
    return history


def _latest_by_probe(readings, point):
    latest = {}
    for aggregate in readings:
        if aggregate['time'] > point:
            continue
        for candidate in candidate_readings(aggregate):
            if candidate.get('time', aggregate['time']) > point:
                continue
            key = candidate.get('probe')
            if not key:
                key = f"_line:{candidate.get('line')}" if candidate.get('line') is not None else '_default'
            current = latest.get(key)
            candidate_time = candidate.get('time', aggregate['time'])
            if current is None or (candidate_time, candidate.get('line', 0)) >= \
                    (current.get('time', aggregate['time']), current.get('line', 0)):
                item = dict(candidate)
                item.setdefault('time', aggregate['time'])
                item.setdefault('end', aggregate['end'])
                item.setdefault('lines', aggregate.get('lines', []))
                latest[key] = item
    return latest


def _matching_decisions(ctx, door, point, scoped_only):
    result = []
    for decision in ctx.decisions:
        if decision['door'] not in (None, door):
            continue
        has_scope = decision.get('start') is not None or decision.get('end') is not None
        if scoped_only and not has_scope:
            continue
        if has_scope:
            start = decision['start']
            end = decision['end']
            if start is not None and point < start:
                continue
            if end is not None and point >= end:
                continue
        result.append(decision)
    return result


def _decision_reading(decision, latest):
    if decision.get('line') is not None:
        for reading in latest.values():
            lines = reading.get('lines') or []
            if decision['line'] == reading.get('line') or decision['line'] in lines:
                return reading
        return None
    if decision.get('probe') is not None:
        return latest.get(decision['probe']) or latest.get('_default')
    # A decision without a probe can still carry a direct temperature verdict.
    if decision.get('warm') is not None:
        return dict(warm=decision['warm'], value='decision', lines=decision.get('lines', []), end=10**12)
    return None


def select_reading(door, point, readings, ctx=None):
    """Return ``(status, reading, info)`` for an OPEN-door slice."""
    latest = _latest_by_probe(readings or [], point)
    if not latest:
        return 'missing', None, {}

    if ctx is not None:
        scoped = _matching_decisions(ctx, door, point, scoped_only=True)
        if scoped:
            signatures = {(d.get('probe'), d.get('line'), d.get('warm')) for d in scoped}
            if len(signatures) > 1:
                lines = sorted({line for decision in scoped for line in decision.get('lines', [])})
                return DISPUTED_KIND, None, dict(reason='handover_conflict', handover_lines=lines)
            reading = _decision_reading(scoped[0], latest)
            if reading is None:
                return 'missing', None, dict(handover_lines=scoped[0].get('lines', []),
                                             probe=scoped[0].get('probe'))
            return 'resolved', reading, dict(handover_lines=scoped[0].get('lines', []),
                                             handover_late=scoped[0].get('late', False),
                                             probe=scoped[0].get('probe'))

    valid = [reading for reading in latest.values()
             if reading.get('warm') is not None and point < reading.get('end', 0)]
    warm_values = {reading['warm'] for reading in valid}
    if len(warm_values) > 1:
        if ctx is not None:
            unscoped = _matching_decisions(ctx, door, point, scoped_only=False)
            unscoped = [d for d in unscoped
                        if d.get('start') is None and d.get('end') is None]
            consistent = {(d.get('probe'), d.get('line')) for d in unscoped}
            if len(consistent) == 1:
                reading = _decision_reading(unscoped[0], latest)
                if reading is not None:
                    return 'resolved', reading, dict(handover_lines=unscoped[0].get('lines', []),
                                                     handover_late=unscoped[0].get('late', False),
                                                     probe=unscoped[0].get('probe'))
            elif len(consistent) > 1:
                lines = sorted({line for d in unscoped for line in d.get('lines', [])})
                return DISPUTED_KIND, None, dict(reason='handover_conflict', handover_lines=lines)
        lines = sorted({line for reading in valid for line in reading.get('lines', [])})
        probes = sorted({str(reading.get('probe')) for reading in valid if reading.get('probe')})
        values = [reading.get('value') for reading in valid]
        return DISPUTED_KIND, None, dict(temperature_lines=lines, probes=probes, values=values)

    if valid:
        reading = max(valid, key=lambda item: (item.get('time', 0), max(item.get('lines') or [0])))
        return 'ok', reading, {}

    # A removed probe must not supply even an expired "latest" reading when a
    # replacement probe exists.  Ordinary TTL-expired readings remain here so
    # the row can retain their source lines while classifying missing_temp.
    current = []
    for reading in latest.values():
        removal = ctx.removal(door, reading.get('probe')) if ctx is not None else None
        if removal is not None and point >= removal:
            continue
        current.append(reading)
    if not current:
        return 'missing', None, {}
    reading = max(current, key=lambda item: (item.get('time', 0), max(item.get('lines') or [0])))
    return 'missing', reading, {}


select = select_reading
reading_at = select_reading
active_reading = select_reading
resolve_reading = select_reading
resolve_probe = select_reading
select_probe = select_reading
normalize = build_context
parse = build_context
load = build_context
read = build_context
