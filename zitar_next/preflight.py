"""Static read-only inventory of an explicitly selected source checkout.

Does not import its code, execute scripts, connect to DBs or enumerate services.
Runtime/production checks are intentionally reserved for the final phase.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path


def inspect(root):
    root=Path(root).resolve(strict=True)
    files=[];imports=set();errors=[]
    for path in sorted(root.rglob('*.py')):
        relative=path.relative_to(root)
        if any(p.startswith('.') or p in ('sources','__pycache__','research_artifacts') for p in relative.parts) or path.is_symlink():
            continue
        raw=path.read_bytes()
        files.append(dict(path=relative.as_posix(),sha256=hashlib.sha256(raw).hexdigest()))
        try:
            tree=ast.parse(raw.decode('utf-8-sig'))
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):
                    imports.update(a.name.split('.')[0] for a in node.names)
                elif isinstance(node,ast.ImportFrom) and node.module:
                    imports.add(node.module.split('.')[0])
        except (SyntaxError,UnicodeError) as exc:
            errors.append(dict(path=relative.as_posix(),error=type(exc).__name__))
    return dict(scope='STATIC_SELECTED_CHECKOUT_ONLY',source=str(root),files=files,import_roots=sorted(imports),parse_errors=errors,
                runtime_verified=False,database_opened=False,services_touched=False,
                final_phase_required=['active entrypoint and installed version','service/scheduled-task inventory',
                                      'configuration and runtime asset paths','DB schema/hash and backup recovery evidence',
                                      'real-order-off end-to-end verification','production regression and integration'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    args=parser.parse_args()
    print(json.dumps(inspect(args.source),indent=2))


if __name__=='__main__':
    main()
