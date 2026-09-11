"""Portable path/size safety tested with disposable files; never touch real data."""
import json
import os
from pathlib import Path
import subprocess
import pytest
from conftest import hashes, put_json
from workflow_author.checker import check_package
from workflow_author.generator import generate


@pytest.mark.parametrize('name', ['../outside.txt', '/absolute.txt', 'C:/temp/value', '//host/share/value',
                                 'components\\bad.py', 'components/../acceptance.md', 'a/./b', 'a//b',
                                 'file.txt:stream', 'NUL.txt', 'folder/name.', 'folder/name '])
def test_manifest_path_rejected_verbatim(completed, name):
    package, _ = completed
    path = package / 'package-manifest.json'
    data = json.loads(path.read_text(encoding='utf-8')); data['acceptance_file'] = name
    put_json(path, data)
    assert check_package(package)['status'] == 'REJECTED'
    assert json.loads(path.read_text(encoding='utf-8'))['acceptance_file'] == name


@pytest.mark.parametrize('bad', ['encoding', 'binary', 'large-file', 'many-files', 'large-total', 'deep-json'])
def test_inputs_are_bounded_and_structured(draft, bad):
    if bad == 'encoding':
        (draft / 'bad.txt').write_bytes(b'\xff\xfe')
    elif bad == 'binary':
        (draft / 'bad.bin').write_bytes(b'a\x00b')
    elif bad == 'large-file':
        (draft / 'bad.txt').write_bytes(b'x' * 2_000_001)
    elif bad == 'many-files':
        for i in range(257):
            (draft / ('extra-' + str(i) + '.txt')).write_text('x')
    elif bad == 'large-total':
        for i in range(11):
            (draft / ('extra-' + str(i) + '.txt')).write_bytes(b'x' * 1_900_000)
    else:
        (draft / 'deep.json').write_text('[' * 2000 + '0' + ']' * 2000)
    result = check_package(draft)
    assert result['status'] == 'REJECTED', result
    assert str(draft) not in json.dumps(result)


def test_hardlink_is_not_followed(draft, tmp_path):
    outside = tmp_path / 'outside.txt'; outside.write_text('do not read')
    os.link(outside, draft / 'linked.txt')
    assert check_package(draft)['status'] == 'REJECTED'
    assert outside.read_text() == 'do not read'


def test_directory_link_and_linked_generation_parent_are_refused(draft, tmp_path):
    outside = tmp_path / 'outside'; outside.mkdir(); (outside / 'keep.txt').write_text('preserve')
    link = draft / 'linked'
    if os.name == 'nt':
        result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(outside, target_is_directory=True)
    try:
        assert check_package(draft)['status'] == 'REJECTED'
        assert generate(link / 'escape')['status'] == 'CONFLICT'
        assert not (outside / 'escape').exists()
        assert (outside / 'keep.txt').read_text() == 'preserve'
    finally:
        os.rmdir(link) if os.name == 'nt' else link.unlink()


def test_same_basename_in_distinct_safe_subdirs_is_not_deduplicated(draft):
    for name in ['one', 'two']:
        (draft / name).mkdir(); (draft / name / 'note.txt').write_text(name)
    before = hashes(draft)
    assert check_package(draft)['status'] == 'DRAFT'
    assert hashes(draft) == before


def test_invalid_root_is_input_rejection_not_internal_error():
    result = check_package('invalid\x00path')
    assert result['status'] == 'REJECTED'


@pytest.mark.parametrize('kind', ['file', 'directory', 'root'])
def test_real_symlink_never_supplies_package_content(draft, tmp_path, kind):
    outside = tmp_path / 'symlink-outside'
    outside.mkdir()
    canary = outside / 'canary.json'
    canary.write_text('{"outside":true}')
    before = canary.read_bytes()
    if kind == 'file':
        (draft / 'linked.json').symlink_to(canary)
        package = draft
    elif kind == 'directory':
        (draft / 'linked-dir').symlink_to(outside, target_is_directory=True)
        package = draft
    else:
        package = tmp_path / 'linked-package'
        package.symlink_to(draft, target_is_directory=True)
    assert check_package(package)['status'] == 'REJECTED'
    assert canary.read_bytes() == before
