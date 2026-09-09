"""Check the exact worktree and changed files against a LOCAL assignment."""
import argparse
import json
import subprocess
from pathlib import Path


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def verify(a):
    root = Path(git('rev-parse', '--show-toplevel')).resolve()
    if root != Path(a['worktree']).resolve() or Path.cwd().resolve() != root:
        raise ValueError('WORKTREE_MISMATCH')
    if git('branch','--show-current') != a['branch'] or a['branch'] == 'main':
        raise ValueError('BRANCH_MISMATCH')
    if not (root/'.git').is_file():
        raise ValueError('WORKTREE_REQUIRED')
    git('merge-base','--is-ancestor',a['base_commit'],'HEAD')
    changed = set()
    for args in [('diff','--name-only','-z',a['base_commit'],'HEAD'),('diff','--name-only','-z'),('diff','--cached','--name-only','-z'),('ls-files','--others','--exclude-standard','-z')]:
        changed.update(filter(None,git(*args).split('\0')))
    if not changed.issubset(a['allowed_files']):
        raise ValueError('FILE_BOUNDARY_VIOLATION')
    return {'verified':True,'issue':a['issue'],'worktree':str(root),'branch':a['branch'],'changed':sorted(changed)}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--assignment',required=True)
    try:
        print(json.dumps(verify(json.loads(Path(parser.parse_args().assignment).read_text(encoding='utf-8'))),ensure_ascii=False))
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        print(json.dumps({'verified':False,'reason':str(exc)}))
        raise SystemExit(2)
