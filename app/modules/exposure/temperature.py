from collections import defaultdict
from decimal import Decimal
import re
from app.settings import TEMP_MAX_AGE
from .probes import PROBE_KEYS, ProbeContext, build_context, epoch, pick

WARM_LIMIT = Decimal('4')


def _probe_name(row):
    return pick(row, PROBE_KEYS)


def normalize(rows, context=None):
    grouped = defaultdict(lambda: defaultdict(list))
    isolated = []
    for row in rows:
        text = row['celsius']
        if not re.fullmatch(r'-?[0-9]{1,3}(?:\.[0-9]{1,3})?', text) or not -90 <= Decimal(text) <= 80:
            isolated.append(dict(row, code='TEMP_INVALID'))
            continue
        probe = _probe_name(row)
        retirement = epoch(pick(row, ('removed_at', 'retired_at', 'remove_at', 'probe_until',
                                     'valid_to', 'end', 'until')))
        retired_flag = pick(row, ('removed', 'retired', 'is_removed', 'is_retired'))
        if retirement is None and retired_flag and retired_flag.lower() in ('1', 'true', 'yes', 'y', '是'):
            retirement = row['time']
        grouped[row['door']][row['time']].append((Decimal(text), row['line'], probe, retirement))
    history = {}
    for door, timestamps in sorted(grouped.items()):
        history[door] = []
        for time, group in sorted(timestamps.items()):
            values = {item[0] for item in group}
            lines = [item[1] for item in group]
            by_probe_preview = defaultdict(set)
            for celsius, _line, probe, _retirement in group:
                by_probe_preview[probe].add(celsius)
            explicit_probe_count = len([probe for probe in by_probe_preview if probe is not None])
            same_probe_conflict = any(probe is not None and len(items) > 1
                                      for probe, items in by_probe_preview.items())
            cross_probe_disagreement_only = (
                explicit_probe_count >= 2 and None not in by_probe_preview and not same_probe_conflict
            )
            if len(values) != 1 and not cross_probe_disagreement_only:
                isolated.append(dict(code='TEMP_CONFLICT', door=door, time=time, lines=lines))
            value = next(iter(values)) if len(values) == 1 else None

            by_probe = defaultdict(list)
            for item in group:
                by_probe[item[2]].append(item)
            candidates = []
            if any(item[2] is None for item in group):
                # Unlabelled rows still need line-level candidates so that a
                # later handover can choose one of two simultaneous probes.
                for celsius, line, probe, retirement in sorted(group, key=lambda item: item[1]):
                    candidates.append(dict(
                        probe=probe,
                        time=time,
                        end=min(time + TEMP_MAX_AGE, retirement) if retirement is not None else time + TEMP_MAX_AGE,
                        value=str(celsius),
                        warm=celsius > WARM_LIMIT,
                        lines=[line],
                        line=line,
                    ))
            for probe, items in sorted(by_probe.items(), key=lambda entry: str(entry[0])):
                if probe is None:
                    continue
                probe_values = {item[0] for item in items}
                probe_lines = [item[1] for item in items]
                probe_value = next(iter(probe_values)) if len(probe_values) == 1 else None
                retirements = [item[3] for item in items if item[3] is not None]
                candidate_end = min([time + TEMP_MAX_AGE] + retirements)
                candidates.append(dict(
                    probe=probe,
                    time=time,
                    end=candidate_end,
                    value=str(probe_value) if probe_value is not None else None,
                    warm=probe_value > WARM_LIMIT if probe_value is not None else None,
                    lines=probe_lines,
                    line=probe_lines[0] if probe_lines else None,
                ))

            explicit_probes = [probe for probe in by_probe if probe is not None]
            entry = dict(time=time, end=time + TEMP_MAX_AGE, value=str(value) if value is not None else None,
                          warm=value > WARM_LIMIT if value is not None else None, lines=lines,
                          candidates=candidates)
            if len(explicit_probes) == 1:
                entry['probe'] = explicit_probes[0]
            elif explicit_probes:
                entry['probe'] = None
            history[door].append(entry)

    # Imported here to avoid a module import cycle at module load time.
    from .probes import apply_context
    if context is not None and not isinstance(context, ProbeContext):
        context = build_context(context)
    apply_context(history, context)
    return history, isolated
