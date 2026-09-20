"""Explicit, user-initiated test execution in an isolated copy of the repository (P3.4).

The user's checkout is never touched: the tree is copied (dependency directories included, so the
project's own runner works), optional proposed file contents are applied to the copy, and each
selected test command runs there without a shell, with a timeout and captured output. Results are
structured and stored so the extension, the API and the loop harness can show them faithfully.
"""
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp

ALLOWED_TOOLS = {'mvn', 'npx', 'npm', 'node', 'pytest', 'python', 'python3', 'gradle', 'go', 'cargo'}
COPY_EXCLUDED = {'.git', '.codemri', '.codemri-preview'}
OUTPUT_LIMIT = 20_000  # characters kept per stream
DEFAULT_TIMEOUT = 300

PYTEST_SUMMARY = re.compile(r'(?:(?P<failed>\d+) failed)?(?:, )?(?:(?P<passed>\d+) passed)?(?:, )?(?:(?P<skipped>\d+) skipped)?(?:, )?(?:(?P<errors>\d+) errors?)?.* in [\d.]+s')
TAP_COUNT = re.compile(r'^# (pass|fail|skipped|cancelled) (\d+)$', re.M)
SUREFIRE = re.compile(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)')
NO_TESTS = re.compile(r'no tests ran|Tests run: 0,|# tests 0\b|No tests found', re.I)


@dataclass
class Command:
    tool: str
    args: list[str]
    label: str = ''


def parse_commands(selection) -> list[Command]:
    """Accept impacted-test selectors (`{'tool','args'}` or the P3.2 test entries) and deduplicate them."""
    seen, commands = set(), []
    for item in selection:
        sel = item.get('selector', item)
        tool, args = sel.get('tool'), list(sel.get('args', []))
        if not tool:
            continue
        if Path(tool).name not in ALLOWED_TOOLS or any(not isinstance(a, str) or '\0' in a for a in args):
            raise ValueError(f'Refusing to run {tool!r}; allowed test tools are {sorted(ALLOWED_TOOLS)}')
        key = (tool, tuple(args))
        if key in seen:
            continue
        seen.add(key)
        commands.append(Command(tool, args, item.get('name') or item.get('path') or ''))
    return commands


def merge_junit(commands: list[Command]) -> list[Command]:
    """Fold many `mvn -Dtest=Class#a`, `-Dtest=Class#b` into one Maven invocation; Maven startup dominates."""
    tests, others, template = [], [], None
    for c in commands:
        spec = next((a for a in c.args if a.startswith('-Dtest=')), None)
        if Path(c.tool).name == 'mvn' and spec:
            tests.append(spec[len('-Dtest='):]); template = c
        else:
            others.append(c)
    if len(tests) > 1 and template:
        args = [('-Dtest=' + ','.join(dict.fromkeys(tests))) if a.startswith('-Dtest=') else a for a in template.args]
        others.insert(0, Command(template.tool, args, f'{len(tests)} JUnit tests'))
    elif tests:
        others.insert(0, template)
    return others


def copy_repository(root: Path) -> Path:
    """Copy `root` to a private temporary directory. Symlinks are kept only when they resolve inside the tree."""
    root = Path(root).resolve()
    directory = Path(mkdtemp(prefix='codemri-run-'))
    work = directory / 'workspace'

    def ignore(directory_, names):
        skip = []
        for name in names:
            source = Path(directory_) / name
            if name in COPY_EXCLUDED:
                skip.append(name)
            elif source.is_symlink():
                target = Path(os.readlink(source))
                if target.is_absolute() or not (source.parent / target).resolve().is_relative_to(root):
                    skip.append(name)
        return skip
    shutil.copytree(root, work, symlinks=True, ignore=ignore)
    return work


def apply_files(work: Path, files) -> list[str]:
    """Write proposed file contents (`{'path','after'}`; `after=None` deletes) into the copy. Never the real checkout."""
    written = []
    for item in files or []:
        rel = Path(item['path'])
        if rel.is_absolute() or any(part in {'..', *COPY_EXCLUDED} for part in rel.parts) or not rel.parts:
            raise ValueError('Invalid proposal path')
        target = work / rel
        if target.is_symlink():
            raise ValueError(f'Refusing to write through a symbolic link: {item["path"]}')
        if item.get('after') is None:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item['after'], encoding='utf-8')
        written.append(item['path'])
    return written


def summarize(tool: str, stdout: str, stderr: str) -> dict:
    text = stdout + '\n' + stderr
    counts = {}
    if m := SUREFIRE.findall(text):
        run, failures, errors, skipped = (sum(int(x[i]) for x in m) for i in range(4))
        counts = {'passed': run - failures - errors - skipped, 'failed': failures + errors, 'skipped': skipped}
    elif m := TAP_COUNT.findall(text):
        found = {k: int(v) for k, v in m}
        counts = {'passed': found.get('pass', 0), 'failed': found.get('fail', 0) + found.get('cancelled', 0), 'skipped': found.get('skipped', 0)}
    elif Path(tool).name in {'pytest', 'python', 'python3'} and (m := PYTEST_SUMMARY.search(text)) and any(m.groupdict().values()):
        g = {k: int(v or 0) for k, v in m.groupdict().items()}
        counts = {'passed': g['passed'], 'failed': g['failed'] + g['errors'], 'skipped': g['skipped']}
    counts['no_tests_ran'] = bool(NO_TESTS.search(text)) or (bool(counts) and counts.get('passed', 0) + counts.get('failed', 0) == 0)
    return counts


def tail(text: str) -> str:
    return text if len(text) <= OUTPUT_LIMIT else '… [truncated] …\n' + text[-OUTPUT_LIMIT:]


def run_command(work: Path, command: Command, timeout: int) -> dict:
    started = time.monotonic()
    env = {k: v for k, v in os.environ.items() if not re.search(r'(KEY|TOKEN|SECRET|PASSWORD)', k, re.I)}
    env['CI'] = '1'
    result = {'tool': command.tool, 'args': command.args, 'label': command.label, 'cwd': str(work)}
    try:
        proc = subprocess.run([command.tool, *command.args], cwd=work, env=env, capture_output=True, text=True,
                              errors='replace', timeout=timeout, stdin=subprocess.DEVNULL)
        result.update(exit_code=proc.returncode, stdout=tail(proc.stdout), stderr=tail(proc.stderr),
                      status='passed' if proc.returncode == 0 else 'failed')
        result['summary'] = summarize(command.tool, proc.stdout, proc.stderr)
        if result['summary'].get('no_tests_ran') and proc.returncode == 0:
            result['status'] = 'no_tests'
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode(errors='replace') if isinstance(exc.stdout, bytes) else (exc.stdout or '')
        err = exc.stderr.decode(errors='replace') if isinstance(exc.stderr, bytes) else (exc.stderr or '')
        result.update(exit_code=None, status='timeout', stdout=tail(out), stderr=tail(err + f'\nTimed out after {timeout}s'), summary={})
    except OSError as exc:
        result.update(exit_code=None, status='error', stdout='', stderr=str(exc), summary={})
    result['duration_ms'] = int((time.monotonic() - started) * 1000)
    return result


def run_tests(root, selection, files=None, timeout: int = DEFAULT_TIMEOUT, keep_copy: bool = False) -> dict:
    """Run the selected tests in a fresh copy of `root` and return a structured, storable result.

    `selection` is the `tests` list from `impact()['tests']` (or raw `{'tool','args'}` selectors); `files`
    are optional proposed file contents applied to the copy first. Nothing is exposed as a read-only MCP
    tool because this executes repository code.
    """
    root = Path(root).resolve()
    commands = merge_junit(parse_commands(selection))
    if not commands:
        return _empty(root, timeout)
    started = time.monotonic()
    work = copy_repository(root)
    try:
        applied = apply_files(work, files)
        result = run_in_copy(work, commands, timeout)
    finally:
        if not keep_copy:
            shutil.rmtree(work.parent, ignore_errors=True)
    result.update(applied_files=applied, root=str(root), duration_ms=int((time.monotonic() - started) * 1000),
                  isolation='temporary copy' + (' (kept at ' + str(work) + ')' if keep_copy else ', deleted after the run'))
    return result


def _empty(root: Path, timeout: int) -> dict:
    return {'status': 'no_tests', 'runs': [], 'applied_files': [], 'root': str(root), 'timeout': timeout,
            'totals': {'passed': 0, 'failed': 0, 'skipped': 0},
            'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'duration_ms': 0,
            'note': 'No runnable test selected; nothing executed.'}


def run_in_copy(work: Path, commands: list[Command], timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Run already-validated commands inside an existing isolated copy (used by the loop harness)."""
    started = time.monotonic()
    runs = [run_command(work, c, timeout) for c in commands]
    status = 'passed' if all(r['status'] == 'passed' for r in runs) else \
        'no_tests' if all(r['status'] in {'passed', 'no_tests'} for r in runs) else \
        'timeout' if any(r['status'] == 'timeout' for r in runs) else 'failed'
    totals = {k: sum(r.get('summary', {}).get(k, 0) for r in runs) for k in ('passed', 'failed', 'skipped')}
    return {'status': status, 'runs': runs, 'applied_files': [], 'timeout': timeout, 'totals': totals,
            'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'duration_ms': int((time.monotonic() - started) * 1000), 'isolation': 'temporary copy',
            'note': 'Executed repository test commands in an isolated copy; the checkout was not modified.'}


def to_json(result: dict) -> str:
    return json.dumps(result, indent=2, sort_keys=True)
