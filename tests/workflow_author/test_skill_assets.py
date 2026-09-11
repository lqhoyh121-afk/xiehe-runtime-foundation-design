"""Delivered repo skill and copied instructions must actually be usable and resolve links."""
import re
from conftest import ROOT


def test_repo_skill_frontmatter_and_local_links(draft):
    skill = ROOT / 'skills/workflow-author/SKILL.md'
    text = skill.read_text(encoding='utf-8')
    assert text.startswith('---\n') and '\n---\n' in text[3:]
    front = text.split('---')[1]
    assert 'name: workflow-author' in front and 'version: 0.1.0' in front
    assert 'author: Laiqh' in front and 'description:' in front
    for target in re.findall(r'\[[^]]+\]\(([^)]+)\)', text):
        assert (skill.parent / target).is_file()
    for filename in ['skills/development-SKILL.md', 'skills/runtime-SKILL.md']:
        body = (draft / filename).read_text(encoding='utf-8')
        assert 'Laiqh' in body and '0.1.0' in body
        for target in re.findall(r'\[[^]]+\]\(([^)]+)\)', body):
            assert ((draft / filename).parent / target).is_file()
    assert 'UNIMPLEMENTED' in (draft / 'skills/runtime-SKILL.md').read_text()
