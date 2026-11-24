from datetime import datetime, timezone
from time import perf_counter_ns
from app.faults import DockFault
from app.pipeline import review
from app.seals import compact, input_seals, sha
from app.settings import VERSION


def save(archive, files):
    begin = perf_counter_ns()
    hashes = input_seals(files)
    key = sha(compact([VERSION, hashes]))
    stages = review(files)
    result = sha(compact(stages))
    stamp = dict(id=key, version=VERSION, inputs=hashes, result_sha256=result, window=stages['window'],
                 elapsed_us=(perf_counter_ns()-begin)//1000, generated_at=datetime.now(timezone.utc).isoformat())
    document, reused = archive.insert(key, stamp, files, stages)
    if document['manifest']['result_sha256'] != result or sha(compact(document['stages'])) != result:
        raise DockFault('DRIFT', '归档与原件复算不一致', 409)
    return dict(brief(document), reused=reused)


def brief(document):
    stamp, stages = document['manifest'], document['stages']
    return dict(id=stamp['id'], manifest=stamp, capacity=stages['capacity']['counts'], exposure=stages['exposure']['counts'])


def current_brief(archive, key):
    document = archive.read(key)
    result = brief(document)
    records = archive.handovers(key)
    if records:
        files = dict(document['files'])
        files['handovers'] = compact(records)
        stages = review(files)
        result.update(exposure=stages['exposure']['counts'],
                      capacity=stages['capacity']['counts'],
                      supplemented=True)
    return result


def handover_payload(body):
    if isinstance(body, dict):
        for key in ('handover', 'handover_record', 'record', 'handovers', 'records',
                    'acceptance', 'acceptances', 'decision', 'decisions'):
            if key in body:
                return body[key]
    return body


def apply_handover(archive, key, body):
    payload = handover_payload(body)
    if payload is None:
        raise DockFault('BAD_HANDOVER', '缺少交接记录')
    record_key = sha(compact(payload))
    existing = archive.handover_stamp(key, record_key)
    if existing is not None:
        return dict(existing, reused=True)

    begin = perf_counter_ns()
    document = archive.read(key)
    records = archive.handovers(key) + [payload]
    files = dict(document['files'])
    files['handovers'] = compact(records)
    stages = review(files)
    result = sha(compact(stages))
    stamp = dict(
        id=key,
        handover_id=record_key,
        record_key=record_key,
        version=VERSION,
        result_sha256=result,
        elapsed_us=(perf_counter_ns() - begin) // 1000,
        generated_at=datetime.now(timezone.utc).isoformat(),
        exposure=stages['exposure']['counts'],
        capacity=stages['capacity']['counts'],
        stages=stages,
    )
    stored, reused = archive.add_handover(key, record_key, stamp, payload)
    if reused:
        return dict(stored, reused=True)
    return dict(stamp, reused=False)


record_handover = apply_handover
submit_handover = apply_handover
save_handover = apply_handover
rerun_handover = apply_handover
