from flask import Blueprint, current_app, jsonify, request
from app.parcels import receive_pack
from .service import apply_handover, brief, current_brief, save

history = Blueprint('history', __name__, url_prefix='/api/receipts')


def receipts():
    return current_app.extensions['ice_receipts']


def request_body():
    body = request.get_json(silent=True)
    if body is not None:
        return body
    text = request.get_data(as_text=True).strip()
    if text:
        return text
    if request.form:
        return request.form.to_dict()
    return None


@history.get('')
def listing():
    rows = receipts().list()
    return jsonify(rows=rows, count=len(rows))


@history.post('')
def publish():
    return jsonify(save(receipts(), receive_pack(request.get_json(silent=True))))


@history.post('/handovers')
def handover_without_key():
    body = request_body()
    payload = body if isinstance(body, dict) else {}
    key = payload.get('id') or payload.get('receipt') or payload.get('receipt_id')
    if not key:
        from app.faults import DockFault
        raise DockFault('NO_RECEIPT', '缺少冷库档案', 404)
    return handover(key)


@history.get('/<key>')
def detail(key):
    return jsonify(current_brief(receipts(), key))


@history.post('/<key>/refresh')
def refresh(key):
    return jsonify(save(receipts(), receipts().read(key)['files']))


@history.post('/<key>/handovers')
@history.post('/<key>/handover')
@history.post('/<key>/acceptances')
@history.post('/<key>/acceptance')
def handover(key):
    return jsonify(apply_handover(receipts(), key, request_body()))
