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
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp

from .ignore import write_copy_marker

ALLOWED_TOOLS = {'mvn', 'npx', 'npm', 'node', 'pytest', 'python', 'python3', 'gradle', 'go', 'cargo'}
COPY_EXCLUDED = {'.git', '.codemri', '.codemri-preview', '.codemri-copy'}
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
    write_copy_marker(root, work)
    return work


def apply_files(work: Path, files) -> list[str]:
    """Write proposed file contents (`{'path','before','after'}`; `after=None` deletes) into the copy. Never the real
    checkout. Paths must resolve inside the copy (no symlinked parents). When `before` is a string it must match
    the copy's current content, so a proposal made against an older revision is rejected as stale instead of
    being tested on top of unrelated edits."""
    written = []
    work = Path(work).resolve()
    for item in files or []:
        rel = Path(item['path'])
        if rel.is_absolute() or any(part in {'..', *COPY_EXCLUDED} for part in rel.parts) or not rel.parts:
            raise ValueError('Invalid proposal path')
        target = work / rel
        if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != work and p.is_relative_to(work)) \
                or not target.parent.resolve().is_relative_to(work):
            raise ValueError(f'Refusing to write through a symbolic link: {item["path"]}')
        before = item.get('before')
        if isinstance(before, str):
            current = target.read_text(encoding='utf-8', errors='replace') if target.is_file() else None
            if current != before:
                raise ValueError(f'Proposal is stale: {item["path"]} changed since the proposal was made; regenerate it')
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
        if 'Results:' in text:  # Maven prints per-class lines and then one aggregate under "Results:"; trust the aggregate.
            m = SUREFIRE.findall(text[text.rindex('Results:'):])[-1:] or m
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


SENSITIVE_ENV = re.compile(r'(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|COOKIE|SESSION|^AWS_|^GOOGLE_|^GCLOUD_|^AZURE_|^GITHUB_|^GH_|^NPM_|^PYPI_|^DOCKER_|^KUBE)', re.I)
ENV_KEEP_VARIABLE = 'CODEMRI_SUBPROCESS_ENV_KEEP'


def scrubbed_env() -> dict[str, str]:
    """Host environment minus credential-shaped variables and agent sockets. Names listed (comma separated) in
    `CODEMRI_SUBPROCESS_ENV_KEEP` are passed through deliberately, e.g. the API key the agent itself needs."""
    keep = {k.strip() for k in os.environ.get(ENV_KEEP_VARIABLE, '').split(',') if k.strip()}
    return {k: v for k, v in os.environ.items() if k in keep or not SENSITIVE_ENV.search(k)}


def safe_path(cwd: Path, env: dict) -> str:
    """Executable lookup never consults the repository copy or relative entries, so a repo cannot ship its own `npx`."""
    cwd = Path(cwd).resolve()
    entries = []
    for entry in (env.get('PATH') or os.defpath).split(os.pathsep):
        p = Path(entry)
        if entry and p.is_absolute() and not p.resolve().is_relative_to(cwd) and entry not in entries:
            entries.append(entry)
    return os.pathsep.join(entries)


def resolve_tool(tool: str, cwd: Path, env: dict) -> str:
    """Bare allow-listed names are resolved against `safe_path`; explicit paths must not point inside the copy."""
    if os.sep in tool or (os.altsep and os.altsep in tool):
        if Path(tool).resolve().is_relative_to(Path(cwd).resolve()):
            raise ValueError(f'Refusing to run an executable inside the repository copy: {tool}')
        return tool
    found = shutil.which(tool, path=safe_path(cwd, env))
    if not found:
        raise OSError(f'{tool!r} not found on PATH')
    return found


class BoundedCapture:
    """Reads a pipe on a thread, keeping only the last `limit` characters so a chatty test cannot exhaust memory."""
    def __init__(self, stream, limit: int = OUTPUT_LIMIT):
        import threading
        self.chunks, self.size, self.limit, self.truncated = [], 0, limit, False
        self.thread = threading.Thread(target=self._drain, args=(stream,), daemon=True)
        self.thread.start()

    def _drain(self, stream):
        with stream:
            while chunk := stream.read(8192):
                self.chunks.append(chunk); self.size += len(chunk)
                while self.size - len(self.chunks[0]) >= self.limit and len(self.chunks) > 1:
                    self.size -= len(self.chunks.pop(0)); self.truncated = True

    def text(self, timeout: float | None = None) -> str:
        self.thread.join(timeout)
        out = ''.join(self.chunks)
        return out if not self.truncated and len(out) <= self.limit else out[-self.limit:]


def run_process(args: list[str], cwd: Path, env: dict, timeout: int, stdin_text: str | None = None) -> subprocess.CompletedProcess:
    """`subprocess.run` that owns the whole process tree: the child starts its own session, and on timeout the
    entire group is terminated (SIGTERM, then SIGKILL) and reaped before `TimeoutExpired` is raised, so launchers
    like npx/mvn cannot leave test processes running against a workspace that is about to be deleted. stdout/stderr
    are drained continuously into bounded buffers (last OUTPUT_LIMIT characters); the executable is resolved on a
    PATH that excludes the copy itself."""
    env = dict(env)
    env['PATH'] = safe_path(cwd, env)
    args = [resolve_tool(args[0], cwd, env), *args[1:]]
    popen_kwargs = {'cwd': cwd, 'env': env, 'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE, 'text': True, 'errors': 'replace',
                    'stdin': subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL}
    if os.name == 'posix':
        popen_kwargs['start_new_session'] = True
    proc = subprocess.Popen(args, **popen_kwargs)
    out, err = BoundedCapture(proc.stdout), BoundedCapture(proc.stderr)
    if stdin_text is not None:
        try:
            proc.stdin.write(stdin_text)
        except (BrokenPipeError, OSError):
            pass
        finally:
            proc.stdin.close()
    deadline = time.monotonic() + timeout
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        proc.wait()
        raise subprocess.TimeoutExpired(args, timeout, output=out.text(5), stderr=err.text(5))
    # The launcher is done; descendants that inherited the pipes (a backgrounded server) would keep them open
    # forever, so give the group the remaining budget, then kill it and stop draining.
    out.thread.join(max(0.0, deadline - time.monotonic())); err.thread.join(max(0.0, deadline - time.monotonic()))
    if out.thread.is_alive() or err.thread.is_alive():
        kill_tree(proc)
        out.thread.join(5); err.thread.join(5)
    return subprocess.CompletedProcess(args, proc.returncode, out.text(0), err.text(0))


def kill_tree(proc: subprocess.Popen, grace: float = 3.0) -> None:
    def signal_group(sig):
        try:
            if os.name == 'posix':
                os.killpg(proc.pid, sig)
            else:
                proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            pass
    signal_group(signal.SIGTERM)
    deadline = time.monotonic() + grace
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    # SIGKILL the group regardless: descendants may have outlived an already-exited launcher.
    signal_group(signal.SIGKILL if os.name == 'posix' else signal.SIGTERM)


def run_command(work: Path, command: Command, timeout: int) -> dict:
    started = time.monotonic()
    env = scrubbed_env()
    env['CI'] = '1'
    result = {'tool': command.tool, 'args': command.args, 'label': command.label, 'cwd': str(work)}
    try:
        proc = run_process([command.tool, *command.args], work, env, timeout)
        result.update(exit_code=proc.returncode, stdout=tail(proc.stdout), stderr=tail(proc.stderr),
                      status='passed' if proc.returncode == 0 else 'failed')
        result['summary'] = summarize(command.tool, proc.stdout, proc.stderr)
        if result['summary'].get('no_tests_ran') and proc.returncode == 0:
            result['status'] = 'no_tests'
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode(errors='replace') if isinstance(exc.stdout, bytes) else (exc.stdout or '')
        err = exc.stderr.decode(errors='replace') if isinstance(exc.stderr, bytes) else (exc.stderr or '')
        result.update(exit_code=None, status='timeout', stdout=tail(out), stderr=tail(err + f'\nTimed out after {timeout}s; process group terminated'), summary={})
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


STATUS_PRECEDENCE = ('error', 'timeout', 'failed', 'passed', 'no_tests')


def aggregate_status(statuses) -> str:
    """Overall status of several commands: error > timeout > failed > passed > no_tests. `no_tests` only when
    every command found nothing; a run that passed real tests is reported as passed."""
    statuses = list(statuses)
    if not statuses:
        return 'no_tests'
    for status in STATUS_PRECEDENCE:
        if status in statuses:
            return status
    return 'error'


def run_in_copy(work: Path, commands: list[Command], timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Run already-validated commands inside an existing isolated copy (used by the loop harness)."""
    started = time.monotonic()
    runs = [run_command(work, c, timeout) for c in commands]
    status = aggregate_status([r['status'] for r in runs])
    totals = {k: sum(r.get('summary', {}).get(k, 0) for r in runs) for k in ('passed', 'failed', 'skipped')}
    return {'status': status, 'runs': runs, 'applied_files': [], 'timeout': timeout, 'totals': totals,
            'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'duration_ms': int((time.monotonic() - started) * 1000), 'isolation': 'temporary copy',
            'note': 'Executed repository test commands in an isolated copy; the checkout was not modified.'}


def to_json(result: dict) -> str:
    return json.dumps(result, indent=2, sort_keys=True)
