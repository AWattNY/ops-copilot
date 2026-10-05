"""
Read-only workspace tools for the Ops Copilot.

These are plain, type-hinted Python functions with docstrings. That's deliberate:
- Phase 0 passes them straight to the Ollama client (it builds JSON schemas from them).
- Phase 1 passes the SAME functions to LangChain's create_agent (it does the same).
The type hints become the input schema; the docstring is what the model reads to
decide when to call the tool. Treat docstrings as API docs for the model.

What these tools enforce (and what they don't):
- Containment: every path the tools touch, including each file search_code opens and
  each entry list_dir reports, is resolved (symlinks followed) and must stay inside
  WORKSPACE. Symlinks pointing outside are skipped or refused, never followed.
- Secret deny-list: .git internals and common secret files (.env, *.pem, *.key, ...)
  are refused by name. This is a convenience, not a guarantee: secrets hard-coded in
  ordinary source files are still readable.
- Bounded work and output: oversized files are skipped, results are truncated, and
  non-regular files (FIFOs, devices) are never opened.
- Errors as strings: expected failures return "ERROR: ..." so the model can recover.

This is NOT an OS-level sandbox. Known gaps (see README "Limitations"): a file swapped
for a symlink between check and open (TOCTOU), hard links to outside files, and
pathological regexes that run for a very long time. Run against repos you trust.
"""

import fnmatch
import os
import re
import stat
from pathlib import Path

WORKSPACE = Path(os.environ.get("AGENT_WORKSPACE", ".")).resolve()

MAX_OUTPUT_CHARS = 12_000          # cap on any single tool result
MAX_FILE_BYTES = 2_000_000         # larger files are skipped by search, refused by read
MAX_LINES_PER_READ = 500           # upper bound for read_file's max_lines

# Noise: not traversed by search_code or shown by list_dir. Explicit reads are allowed
# (reading library source under node_modules can be legitimate).
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}

# Policy: refused for every tool, by any path component (dirs) or file name (patterns).
DENIED_DIRS = {".git"}
DENIED_FILE_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
    "id_rsa*", "id_ed25519*", "id_ecdsa*", ".netrc", ".pgpass", ".npmrc", ".pypirc",
]
ALLOWED_DESPITE_PATTERN = {".env.example", ".env.sample", ".env.template"}


def _is_denied(rel: Path) -> bool:
    """True if a workspace-relative path is blocked by the secret deny-list."""
    if any(part in DENIED_DIRS for part in rel.parts):
        return True
    name = rel.name
    if name in ALLOWED_DESPITE_PATTERN:
        return False
    return any(fnmatch.fnmatch(name, pat) for pat in DENIED_FILE_PATTERNS)


def _check(path: Path) -> Path:
    """Resolve `path` (following symlinks) and enforce containment + deny-list.

    Both the path as named and the resolved target are checked, so neither a
    harmless-looking link to `.env` nor a `.env` link elsewhere slips through.
    Returns the resolved path; raises ValueError on violation.
    """
    resolved = path.resolve()
    if not resolved.is_relative_to(WORKSPACE):
        raise ValueError("path is outside the workspace")
    lexical = Path(os.path.normpath(path))
    for candidate in (lexical, resolved):
        if candidate.is_relative_to(WORKSPACE) and _is_denied(candidate.relative_to(WORKSPACE)):
            raise ValueError("path is blocked by the workspace secret policy")
    return resolved


def _safe_path(rel_path: str) -> Path:
    """Check a model-supplied path. Absolute paths and '..' escapes are refused."""
    try:
        return _check(WORKSPACE / rel_path)
    except ValueError as e:
        raise ValueError(f"'{rel_path}': {e}") from None


def _is_regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.stat().st_mode)
    except OSError:
        return False


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(text) - MAX_OUTPUT_CHARS} more chars]"


def list_dir(path: str = ".") -> str:
    """List files and subdirectories at a path inside the workspace.

    Args:
        path: Directory path relative to the workspace root. Defaults to the root.
    """
    try:
        target = _safe_path(path)
    except ValueError as e:
        return f"ERROR: {e}"
    if not target.is_dir():
        return f"ERROR: '{path}' is not a directory"

    entries, hidden = [], 0
    try:
        children = sorted(target.iterdir())
    except OSError as e:
        return f"ERROR: could not list '{path}': {e.strerror or e}"

    for child in children:
        if child.name in SKIP_DIRS:
            continue
        try:
            _check(child)
        except ValueError:
            hidden += 1  # outside link or denied file: don't reveal its target or size
            continue
        label = str(child.relative_to(WORKSPACE))
        try:
            if child.is_dir():
                entries.append(label + "/")
            else:
                entries.append(f"{label}  ({child.stat().st_size} bytes)")
        except OSError:
            entries.append(f"{label}  (broken link)")

    if hidden:
        entries.append(f"({hidden} entries hidden by workspace policy)")
    return _truncate("\n".join(entries) or "(empty directory)")


def read_file(path: str, start_line: int = 1, max_lines: int = 200) -> str:
    """Read a text file from the workspace, with line numbers.

    Args:
        path: File path relative to the workspace root.
        start_line: 1-based line to start from. Use this to page through long files.
        max_lines: Maximum number of lines to return (1-500).
    """
    try:
        target = _safe_path(path)
    except ValueError as e:
        return f"ERROR: {e}"
    if not _is_regular_file(target):
        return f"ERROR: '{path}' is not a regular file. Use list_dir to find valid paths."

    try:
        if target.stat().st_size > MAX_FILE_BYTES:
            return f"ERROR: '{path}' is larger than {MAX_FILE_BYTES} bytes; use search_code instead."
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"ERROR: could not read '{path}': {e.strerror or e}"

    start = max(int(start_line), 1) - 1
    count = min(max(int(max_lines), 1), MAX_LINES_PER_READ)
    if start >= len(lines) and lines:
        return f"ERROR: start_line {start + 1} is past the end; file has {len(lines)} lines."

    chunk = lines[start : start + count]
    numbered = [f"{i + start + 1:>5} | {line}" for i, line in enumerate(chunk)]
    footer = ""
    if start + count < len(lines):
        footer = f"\n... file has {len(lines)} lines; call again with start_line={start + count + 1}"
    return _truncate("\n".join(numbered) + footer)


def search_code(pattern: str, path: str = ".", max_results: int = 50) -> str:
    """Search files in the workspace for a regular expression, like grep -rn.

    Args:
        pattern: Python regular expression to search for.
        path: Directory to search under, relative to the workspace root.
        max_results: Maximum number of matching lines to return.
    """
    try:
        root = _safe_path(path)
        regex = re.compile(pattern)
    except (ValueError, re.error) as e:
        return f"ERROR: {e}"
    if not root.is_dir():
        return f"ERROR: '{path}' is not a directory"

    max_results = max(1, int(max_results))
    hits = []
    # followlinks=False: symlinked directories are listed but never descended into.
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and d not in DENIED_DIRS)
        for name in sorted(filenames):
            file_path = Path(dirpath) / name
            try:
                resolved = _check(file_path)  # the per-file check the original code lacked
            except ValueError:
                continue
            if not _is_regular_file(resolved):
                continue  # FIFOs/devices would block or misbehave on open()
            try:
                if resolved.stat().st_size > MAX_FILE_BYTES:
                    continue
                with resolved.open(encoding="utf-8", errors="strict") as f:
                    for lineno, line in enumerate(f, start=1):
                        if regex.search(line):
                            rel = file_path.relative_to(WORKSPACE)
                            hits.append(f"{rel}:{lineno}: {line.rstrip()[:200]}")
                            if len(hits) >= max_results:
                                return _truncate("\n".join(hits) + "\n... [max_results reached]")
            except (UnicodeDecodeError, OSError):
                continue  # skip binaries and unreadable files
    return _truncate("\n".join(hits) or "No matches.")


TOOLS = [list_dir, read_file, search_code]
