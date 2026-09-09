"""Local content-addressed snapshots. Integrity checks are NOT signatures/auth."""
import hashlib
import os
import tempfile
from pathlib import Path

from input_contract import ContractError, Snapshot, canonical


def save_snapshot(snapshot, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (snapshot.snapshot_id + '.json')
    raw = snapshot.payload.encode('utf-8')
    fd, temporary = tempfile.mkstemp(prefix='.snapshot-', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # Atomic create without replacing any existing content.
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != raw:
                raise ContractError('SNAPSHOT_CORRUPT')
        return target
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_snapshot(path):
    path = Path(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != path.stem:
        raise ContractError('SNAPSHOT_CORRUPT')
    try:
        snapshot = Snapshot(raw.decode('utf-8'))
        doc = snapshot.to_dict()
        if doc.get('contract') != 'observation-input-spike/1' or canonical(doc) != snapshot.payload:
            raise ValueError('not a canonical supported snapshot')
        return snapshot
    except (ValueError, UnicodeError, AttributeError) as exc:
        raise ContractError('SNAPSHOT_CORRUPT') from exc
