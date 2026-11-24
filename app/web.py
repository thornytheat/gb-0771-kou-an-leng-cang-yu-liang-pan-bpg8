from flask import Blueprint, jsonify, render_template, request
from .faults import DockFault
from .labels import TABS, CODES, KINDS
from .modules.certificate.service import issue
from .modules.history.routes import receipts, request_body
from .modules.history.service import apply_handover
from .parcels import load_example, receive_pack
from .pipeline import review
from .seals import compact
from .swimlanes import lanes, minutes
from .utc import iso

board = Blueprint('board', __name__)


def selection():
    key, example = request.args.get('receipt'), request.args.get('sample', 'dirty')
    if key:
        archive = receipts()
        doc = archive.read(key)
        stages, stamp = doc['stages'], doc['manifest']
        handover_records = archive.handovers(key)
        if handover_records:
            files = dict(doc['files'])
            files['handovers'] = compact(handover_records)
            stages = review(files)
        return stages, stamp, example
    return review(load_example(example)), None, example


@board.get('/api/observe/<view>')
def observe(view):
    if view not in tuple(TABS)[:5]:
        raise DockFault('NO_VIEW', '未找到查验入口', 404)
    key = request.args.get('receipt')
    if key:
        stages, _, _ = selection()
        return jsonify(stages[view])
    return jsonify(review(load_example(request.args.get('sample', 'dirty')), until=view))


@board.post('/api/observe/<view>')
def inspect_originals(view):
    if view not in tuple(TABS)[:5]:
        raise DockFault('NO_VIEW', '未找到查验入口', 404)
    return jsonify(review(receive_pack(request.get_json(silent=True)), until=view))


@board.post('/api/handovers')
@board.post('/api/handover')
@board.post('/api/probe-handovers')
def inspect_handover():
    body = request.get_json(silent=True)
    if isinstance(body, dict) and isinstance(body.get('files'), dict):
        pack = receive_pack(body['files'])
        for key in ('handovers', 'handover', 'acceptances', 'probes'):
            if key in body:
                pack[key] = body[key] if isinstance(body[key], str) else compact(body[key])
    elif isinstance(body, dict) and isinstance(body.get('pack'), dict):
        pack = receive_pack(body['pack'])
    else:
        pack = receive_pack(body)
    return jsonify(review(pack, until='exposure'))


@board.post('/api/handovers/<key>')
@board.post('/api/handover/<key>')
@board.post('/api/receipt/<key>/handovers')
@board.post('/api/receipt/<key>/handover')
def handover_for_receipt(key):
    return jsonify(apply_handover(receipts(), key, request_body()))


@board.get('/', defaults={'view':'exposure'})
@board.get('/view/<view>')
def page(view):
    if view not in TABS:
        raise DockFault('NO_VIEW', '未找到查验入口', 404)
    stages, stamp, example = selection()
    if view == 'certificate' and stamp:
        issue(receipts().read(stamp['id']))
    tracks, ticks = lanes(stages)
    return render_template('station.html', stages=stages, view=view, stamp=stamp, sample=example, tabs=TABS,
                           codes=CODES, kinds=KINDS, tracks=tracks, ticks=ticks, utc=iso, minutes=minutes,
                           entries=receipts().list() if view == 'history' else [])
