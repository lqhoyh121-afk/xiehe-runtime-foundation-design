"""Deterministic draft templates; no publication, permissions or business defaults. Laiqh."""
import json
from pathlib import Path
from .contracts import ACCEPTANCE_SECTIONS, COMPONENT, MANIFEST, draft_fields

ASSETS = Path(__file__).resolve().parents[1] / 'skills/workflow-author'


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def draft_files():
    manifest, component = draft_fields(MANIFEST), draft_fields(COMPONENT)
    return {
        'package-manifest.json': json_text(manifest),
        manifest['projection_file']: 'null\n',
        manifest['component_files'][0]: json_text(component),
        component['implementation_file']: '"""Draft component. Laiqh."""\ndef normalize(value):\n    raise NotImplementedError("Author implementation required")\n',
        component['test_files'][0]: '"""Draft tests. Laiqh."""\ndef test_author_must_supply_independent_expectations():\n    raise NotImplementedError("Author tests required")\n',
        'skills/development-SKILL.md': (ASSETS / 'references/author-guide.md').read_text(encoding='utf-8'),
        'skills/runtime-SKILL.md': (ASSETS / 'templates/runtime-SKILL.md').read_text(encoding='utf-8'),
        'acceptance.md': '# Author acceptance / Laiqh\n\n' + '\n'.join('## ' + name + '\nTODO: author declaration required.\n' for name in ACCEPTANCE_SECTIONS),
    }
