"""Read-only source syntax and credential checks before checkpoint publication.

Print filenames and check outcomes only; never print matched credential values.
This is a release check, not a replacement for the Modal regression suite.
"""
from pathlib import Path
import ast
import os
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    listed = subprocess.check_output(
        ['git', 'ls-files', '-c', '-o', '--exclude-standard', '-z'], cwd=ROOT,
    ).decode().split('\0')
    paths = sorted({ROOT / value for value in listed if value})
    secret_name = re.compile(r'KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL', re.I)
    secrets = {value for name, value in os.environ.items()
               if secret_name.search(name) and len(value) >= 12}
    env_file = ROOT / '.env'
    if env_file.is_file():
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            if '=' not in line or line.lstrip().startswith('#'):
                continue
            name, value = line.split('=', 1)
            value = value.strip().strip('\"\'')
            if secret_name.search(name) and len(value) >= 12:
                secrets.add(value)
    patterns = [
        re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
        re.compile(rb'github_pat_[A-Za-z0-9_]{40,}'),
        re.compile(rb'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----'),
    ]
    failures, python_count = [], 0
    for path in paths:
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if (path.name == '.env' or path.name.startswith('.env.')
                or relative.startswith(('data/', '.aws/', '.ssh/'))):
            failures.append((relative, 'prohibited publication path'))
            continue
        if path.stat().st_size > 20 * 1024 * 1024:
            failures.append((relative, 'unexpected file larger than 20 MiB'))
            continue
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=relative)
            python_count += 1
        if path.suffix in ('.docx', '.xlsx'):
            with zipfile.ZipFile(path) as archive:
                bodies = [archive.read(name) for name in archive.namelist()
                          if name.endswith(('.xml', '.rels'))]
        else:
            bodies = [path.read_bytes()]
        if any(any(secret.encode() in body for secret in secrets)
               or any(pattern.search(body) for pattern in patterns)
               for body in bodies):
            failures.append((relative, 'credential match; value suppressed'))
    print(f'Checked {len(paths)} publication files; Python syntax: {python_count} files.')
    if failures:
        for relative, reason in failures:
            print(f'FAIL: {relative}: {reason}')
        raise SystemExit(1)
    print('PASS: no detected credentials, prohibited paths or oversized files.')


if __name__ == '__main__':
    main()
