"""Conservative export scan. Reports paths/rules only, never matched secrets."""
import json
from pathlib import Path
import re
import subprocess


def audit():
    paths = subprocess.check_output(['git','ls-files','-z']).decode().split('\0')
    failures=[]
    for name in filter(None,paths):
        if re.search(r'(^|/)(\.local|\.env[^/]*|evidence|__pycache__|backups|node_modules|\.dev-flow)(/|$)|\.(db|sqlite\w*|log|bak|zip|xlsx|pem|key)$',name,re.I):
            failures.append((name,'excluded-path')); continue
        raw=Path(name).read_bytes()
        if b'\0' in raw:
            failures.append((name,'binary')); continue
        text=raw.decode('utf-8')
        rules={
            'machine-path':r'[A-Za-z]:[/\\]Users[/\\]',
            'private-key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
            'token':r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})',
            'credential-url':r'https?://[^\s/@]+:[^\s/@]+@',
            'literal-secret':r'''(?i)(?:password|passwd|access_token|client_secret|api_key)\s*[=:]\s*["'][^"'\n]{8,}["']''',
        }
        for rule,pattern in rules.items():
            if re.search(pattern,text): failures.append((name,rule))
    return {'files':len([p for p in paths if p]),'findings':failures}


if __name__=='__main__':
    result=audit();print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(bool(result['findings']))
