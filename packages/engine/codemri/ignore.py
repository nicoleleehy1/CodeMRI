"""Repository walk shared by the analyzer, the inventory and AI excerpts.

Honours `.gitignore` files (root and nested), skips virtual environments and build residue,
and excludes secret-shaped files so their contents never reach the graph, a snapshot or a model.
Everything skipped is reported so the exclusion is visible rather than silent.
"""
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
import os
import re

SKIP_DIRS = {'node_modules', '.git', '.hg', '.svn', '.venv', 'venv', 'dist', 'build', 'coverage', '.next', '.codemri',
             '.codemri-preview', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'target', 'vendor', '.tox', '.idea'}
SECRET_FILES = ('.env', '.env.*', '*.pem', '*.key', '*.p12', '*.pfx', '*.jks', '*.keystore', 'id_rsa*', 'id_ed25519*', 'id_ecdsa*',
                '*.secret', '*.secrets', 'secrets.*', 'credentials', 'credentials.*', '*credentials.json', 'service-account*.json',
                '.npmrc', '.pypirc', '.netrc', '.htpasswd', '*.tfvars', '.aws', '.docker/config.json')
SECRET_FILE_EXCEPTIONS = ('.env.example', '.env.sample', '.env.template', '.env.dist')

# Secret-shaped strings that must not be forwarded in AI excerpts even when the file itself is analyzed.
SECRET_TEXT = re.compile(
    r'(?P<key>sk-[A-Za-z0-9_\-]{16,}|sk_(?:live|test)_[A-Za-z0-9]{8,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}'
    r'|xox[abprs]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----'
    r'|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})'
    r'|(?P<assign>(?i:password|passwd|secret|token|api[_-]?key|private[_-]?key|client[_-]?secret)\s*[:=]\s*[\'"]?)(?P<value>[^\s\'",;]{8,})')


def redact_secrets(text: str) -> tuple[str, int]:
    """Replace secret-shaped values with a marker. Returns (text, number of redactions)."""
    count = 0
    def swap(match):
        nonlocal count
        count += 1
        if match.group('key'):
            return '[redacted-secret]'
        return match.group('assign') + '[redacted-secret]'
    return SECRET_TEXT.sub(swap, text), count


@dataclass
class Rule:
    pattern: str
    negated: bool
    directory_only: bool
    anchored: bool
    base: str  # directory (posix, '' for root) the .gitignore lives in

    def matches(self, relative: str, is_dir: bool) -> bool:
        if self.directory_only and not is_dir:
            return False
        if self.base:
            if not relative.startswith(self.base + '/'):
                return False
            relative = relative[len(self.base) + 1:]
        if self.anchored or '/' in self.pattern:
            return fnmatchcase(relative, self.pattern) or fnmatchcase(relative, self.pattern.rstrip('/'))
        return any(fnmatchcase(part, self.pattern) for part in relative.split('/'))


def parse_gitignore(text: str, base: str) -> list[Rule]:
    rules = []
    for raw in text.splitlines():
        line = raw.rstrip('\n')
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        line = line.rstrip(' ') if not line.endswith('\\ ') else line
        negated = line.startswith('!')
        if negated:
            line = line[1:]
        if line.startswith('\\'):
            line = line[1:]
        directory_only = line.endswith('/')
        line = line.rstrip('/')
        anchored = line.startswith('/') or ('/' in line)
        line = line.lstrip('/')
        if line.startswith('**/'):
            line = line[3:]
            anchored = False
        if not line:
            continue
        rules.append(Rule(line, negated, directory_only, anchored, base))
    return rules


def is_secret_file(name: str) -> bool:
    if name in SECRET_FILE_EXCEPTIONS:
        return False
    return any(fnmatchcase(name, pattern) for pattern in SECRET_FILES)


def is_virtualenv(directory: Path) -> bool:
    name = directory.name
    return name in {'.venv', 'venv'} or name.startswith(('.venv-', 'venv-', '.venv_', 'venv_')) or (directory / 'pyvenv.cfg').is_file()


@dataclass
class Walk:
    """Result of walking a repository: file paths (posix, relative) and what was left out and why."""
    files: list[str] = field(default_factory=list)
    skipped: dict[str, list[str]] = field(default_factory=lambda: {'gitignored': [], 'secret': [], 'virtualenv': [], 'residue': []})

    def summary(self) -> list[str]:
        return [f'Skipped {len(paths)} {reason} path(s): ' + ', '.join(paths[:5]) + (' …' if len(paths) > 5 else '')
                for reason, paths in self.skipped.items() if paths]


class Ignorer:
    def __init__(self, root: Path):
        self.root = root
        self.rules: list[Rule] = []
        self.load(root, '')

    def load(self, directory: Path, base: str):
        gitignore = directory / '.gitignore'
        if gitignore.is_file():
            try:
                self.rules.extend(parse_gitignore(gitignore.read_text(errors='replace'), base))
            except OSError:
                pass

    def ignored(self, relative: str, is_dir: bool) -> bool:
        result = False
        for rule in self.rules:
            if rule.matches(relative, is_dir):
                result = not rule.negated
        if not result and '/' in relative:
            # A file under an ignored directory is ignored even if a later rule negates the file itself.
            parent = relative.rsplit('/', 1)[0]
            return self.ignored(parent, True)
        return result


def walk_repository(root: Path) -> Walk:
    """Files under `root` that analysis may read, in sorted order, with skip diagnostics."""
    root = Path(root).resolve()
    result = Walk()
    ignorer = Ignorer(root)
    for directory, dirs, names in os.walk(root, followlinks=False):
        here = Path(directory)
        base = here.relative_to(root).as_posix() if here != root else ''
        if base:
            ignorer.load(here, base)
        kept = []
        for d in sorted(dirs):
            child = here / d
            relative = f'{base}/{d}' if base else d
            if child.is_symlink():
                continue
            if d in SKIP_DIRS or d.endswith('.egg-info'):
                result.skipped['residue'].append(relative + '/')
            elif is_virtualenv(child):
                result.skipped['virtualenv'].append(relative + '/')
            elif ignorer.ignored(relative, True):
                result.skipped['gitignored'].append(relative + '/')
            elif is_secret_file(d):
                result.skipped['secret'].append(relative + '/')
            else:
                kept.append(d)
        dirs[:] = kept
        for name in sorted(names):
            file = here / name
            relative = f'{base}/{name}' if base else name
            if file.is_symlink():
                continue
            if is_secret_file(name):
                result.skipped['secret'].append(relative)
            elif ignorer.ignored(relative, False):
                result.skipped['gitignored'].append(relative)
            else:
                result.files.append(relative)
    result.files.sort()
    for paths in result.skipped.values():
        paths.sort()
    return result
