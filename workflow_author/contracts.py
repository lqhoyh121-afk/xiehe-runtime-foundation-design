"""Author-owned WF0 metadata only; shared runtime schema is never copied. Laiqh."""
from copy import deepcopy

VERSION = '0.1.0'
PROFILE = 'single-code-output-v1'
EXIT_CODES = {'CREATED': 0, 'PASSED': 0, 'DRAFT': 2, 'REJECTED': 3,
              'INCOMPLETE': 4, 'CONFLICT': 5, 'USAGE_ERROR': 64, 'INTERNAL_ERROR': 1}
FAILURE_KEYS = ('input_invalid', 'missing_material', 'rule_rejected',
                'dependency_unavailable', 'output_invalid', 'result_unknown')
ACCEPTANCE_SECTIONS = ('输入', '独立预期', '检查子集', '材料来源', '人工/运行未验证项', '待决表达')
# key -> author type, draft value. Shared references live ONLY in projection_file.
MANIFEST = {
    'author_contract_version': ('version', VERSION),
    'package_id': ('id', 'wf0-static-normalize'),
    'author_version': ('version', VERSION),
    'candidate_state': ('state', 'draft'),
    'projection_file': ('file', 'definitions/workflow-projection.json'),
    'static_profile': ('profile', PROFILE),
    'required_core_capabilities': ('capabilities', [
        {'interface': 'I1', 'requirement': '受信注册'},
        {'interface': 'I2', 'requirement': '纯组件绑定执行'},
        {'interface': 'I8', 'requirement': '当前权限和失败裁定'}]),
    'component_files': ('files', ['components/normalize-submission/declaration.json']),
    'acceptance_file': ('file', 'acceptance.md'),
}
COMPONENT = {
    'component_id': ('id', 'normalize-submission'),
    'author_version': ('version', VERSION),
    'node_id': ('id', 'normalize'),
    'purpose': ('text', '删除输入text两端U+0020空格，保留内部字符'),
    'non_goals': ('texts', ['不获取补料、不串调、不写外部目标']),
    'implementation_file': ('file', 'components/normalize-submission/implementation.py'),
    'test_files': ('files', ['components/normalize-submission/test_normalize.py']),
    'implementation_state': ('implementation', 'unimplemented'),
    'allowed_helpers': ('optional_files', []),
    'permissions': ('permissions', [{'need': '只读当前固定输入并返回候选输出', 'scope_note': '仅当前输入，不跨Case读取'}]),
    'side_effects': ('effects', {'category': 'none', 'intent_note': None, 'idempotency_note': None, 'readback_note': None}),
    'failure_notes': ('failures', dict(zip(FAILURE_KEYS, [
        '拒绝非模型输入，不自动转换类型', '缺text拒绝，不等待或补事实',
        '由核心按规则接缝裁定，不返回合格输出', '报告依赖不可得，不用缓存或模型代判',
        '拒绝输出候选，不推进状态', '无外部动作，不将故障当成功或自行重试']))),
    'completion_evidence_note': ('text', 'OUTPUT_VALIDATED；校验normalized与当前输入关联；不写Case完成'),
}
LIMITATIONS = [
    'Static metadata and bounded source screening only; not a Python sandbox.',
    'Component tests, model/rule evaluation, provider code binding and business review are separate.',
    'I3/I4/I6 mapping, waiting and external ports are unsupported; no runtime or current permission proof.',
]


def draft_fields(fields):
    return {key: deepcopy(value) for key, (_, value) in fields.items()}


def report(operation, status, *, profile=PROFILE, checks=None, diagnostics=None):
    return dict(report_version=VERSION, tool_version=VERSION, template_version=VERSION,
                rules_version=VERSION, operation=operation, status=status, profile=profile,
                checks=checks or [], diagnostics=diagnostics or [], limitations=list(LIMITATIONS),
                runtime_verified=False, production_authorized=False)


def diagnostic(ident, *, source_code=None, file=None, pointer=None, line=None, column=None,
               message='Input does not satisfy the declared contract.',
               remediation='Correct the located declaration; do not bypass the gate.', phase='structure'):
    # Callers use fixed messages/locations only, never exception strings or input values.
    return dict(id=ident, source_code=source_code, severity='ERROR', file=file, pointer=pointer,
                line=line, column=column, message=message, remediation=remediation, phase=phase)
