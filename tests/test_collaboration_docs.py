"""Public collaboration entry points only; historical evidence is not exported."""
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRIES = ('README.md', 'AGENTS.md', 'PROJECT_CONTROL.md',
           'docs/collaboration/START.md', 'docs/collaboration/GOVERNANCE.md')


def broken_links(root, text):
    errors = []
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
        if target.startswith(('https://', 'http://', '#')):
            continue
        path = (root / target.split('#')[0]).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            errors.append(target)
    return errors


@pytest.mark.parametrize('entry', ENTRIES)
def test_entry_links(entry):
    path = ROOT / entry
    assert path.is_file(), entry
    assert not broken_links(path.parent, path.read_text(encoding='utf-8'))


def test_public_scope_and_governance_navigation():
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert '公开协作仓库' in text
    assert '[保护规则](docs/collaboration/GOVERNANCE.md)' in text


def test_missing_and_escaping_links_fail_closed():
    assert broken_links(ROOT, '[bad](nonexistent-collaboration-file.md)')
    assert broken_links(ROOT, '[bad](../AGENTS.md)')
    assert not broken_links(ROOT, '[valid](AGENTS.md)')


def test_external_urls_are_not_claimed_verified():
    assert not broken_links(ROOT, '[remote](https://example.invalid)')
