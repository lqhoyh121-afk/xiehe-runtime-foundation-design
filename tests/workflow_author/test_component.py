"""Execute only this explicitly authored synthetic component, never check-import arbitrary code."""
import importlib.util
import subprocess
import sys
import pytest
from conftest import ROOT, IMPLEMENTATION, hashes


@pytest.fixture
def component(tmp_path):
    path = tmp_path / 'independent_component.py'
    path.write_text(IMPLEMENTATION, encoding='utf-8')
    spec = importlib.util.spec_from_file_location('explicit_synthetic_component', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.normalize


@pytest.mark.parametrize('text,expected', [('  SYNTHETIC  sample  ', 'SYNTHETIC  sample'), ('汉字  text', '汉字  text'),
                                          ('\tvalue\t', '\tvalue\t'), ('plain', 'plain')])
def test_normalize_independent_expected_and_repeat(component, text, expected):
    value = {'text': text}
    assert component(value) == {'normalized': expected}
    assert component(value) == {'normalized': expected}
    assert value == {'text': text}


@pytest.mark.parametrize('value,code', [({}, 'MODEL_REJECTED'), ({'text': 42}, 'MODEL_REJECTED'),
                                     ({'text': 'a', 'extra': True}, 'MODEL_REJECTED')])
def test_component_rejects_bad_inputs_separately(component, value, code):
    with pytest.raises(ValueError, match=code):
        component(value)


@pytest.mark.parametrize('text,allowed,normalized', [('', False, ''), ('   ', False, ''), (' a ', True, 'a')])
def test_rule_precondition_is_separate_from_the_pure_component(component, text, allowed, normalized):
    # Independent test oracle for the published rule requirement, NOT a runtime RuleProvider.
    rule_allows = any(character != ' ' for character in text)
    assert rule_allows is allowed
    # A transformation result is not a rule decision or business completion.
    assert component({'text': text}) == {'normalized': normalized}


def test_component_tests_use_actual_generated_file_entry(completed):
    package, _ = completed
    before = hashes(package)
    p = subprocess.run([sys.executable, '-B', '-m', 'pytest', str(package / 'components/normalize-submission/test_normalize.py'),
                        '-q', '-p', 'no:cacheprovider'], cwd=ROOT, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert '1 passed' in p.stdout
    assert before == hashes(package)
