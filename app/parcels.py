from collections.abc import Mapping

from .faults import DockFault
from .settings import EXAMPLES, PARTS
from .seals import compact


def load_example(name):
    if name not in ('dirty', 'clean'):
        raise DockFault('NO_SAMPLE', '找不到口岸样例', 404)
    ext = {part: 'json' if part == 'window' else 'csv' for part in PARTS}
    return {part: (EXAMPLES / name / f'{part}.{ext[part]}').read_bytes().decode() for part in PARTS}


def receive_pack(body):
    if isinstance(body, dict) and set(body) == {'sample'}:
        return load_example(body['sample'])
    if isinstance(body, Mapping) and body.get('sample'):
        files = load_example(body['sample'])
        for key, value in body.items():
            if key == 'sample':
                continue
            files[key] = value if isinstance(value, str) else compact(value)
        return files
    if isinstance(body, Mapping) and set(PARTS).issubset(body):
        files = {}
        for key, value in body.items():
            if isinstance(value, str):
                files[key] = value
            elif key not in PARTS and value is not None:
                files[key] = compact(value)
        if all(isinstance(files.get(part), str) for part in PARTS):
            return files
    raise DockFault('BAD_PACK', '提交样例或完整六份原件')
