"""Strict unified-diff parsing; reject ambiguous/truncated snapshots."""

import fnmatch
import re

from shrike.domain.review import (
    Coverage,
    ReviewError,
    ReviewInput,
    ReviewLimits,
    SelectedFile,
    safe_path,
)

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")


def select_files(
    request: ReviewInput, limits: ReviewLimits
) -> tuple[tuple[SelectedFile, ...], Coverage]:
    if len(request.diff.encode("utf-8")) > limits.max_diff_bytes:
        raise ReviewError("diff_size_limit")
    if len(request.files) > 1000 or sum(len(f.content.encode()) for f in request.files) > 4194304:
        raise ReviewError("snapshot_size_limit")
    sources = {file.path: file for file in request.files}
    if len(sources) != len(request.files):
        raise ReviewError("duplicate_source_path")
    lines = request.diff.splitlines()
    changes: dict[str, set[int]] = {}
    expected: dict[str, dict[int, str]] = {}
    unsupported: set[str] = set()
    path: str | None = None
    old_left = new_left = new_line = 0
    seen_hunk = False
    last_end = 0
    header_seen = False
    old_header = False
    binary_body = False
    for line in lines:
        if binary_body and not line.startswith("diff --git "):
            continue
        if line == "\\ No newline at end of file":
            continue
        if line.startswith("diff --git "):
            if (
                old_left
                or new_left
                or (path is not None and not seen_hunk and path not in unsupported)
            ):
                raise ReviewError("incomplete_diff")
            match = re.fullmatch(r"diff --git a/(.+) b/(.+)", line)
            if not match:
                raise ReviewError("unsupported_diff_path")
            try:
                safe_path(match[1])
                path = safe_path(match[2])
            except ValueError:
                raise ReviewError("unsafe_diff_path") from None
            if path in changes:
                raise ReviewError("duplicate_diff_path")
            changes[path], expected[path] = set(), {}
            seen_hunk = header_seen = old_header = False
            last_end = 0
            binary_body = False
        elif path is None:
            if line:
                raise ReviewError("invalid_diff")
        elif old_left or new_left:
            if not line or line[0] not in " +-":
                raise ReviewError("invalid_hunk")
            marker = line[0]
            if marker != "+":
                old_left -= 1
            if marker != "-":
                new_left -= 1
                expected[path][new_line] = line[1:]
                if marker == "+":
                    changes[path].add(new_line)
                new_line += 1
            if old_left < 0 or new_left < 0:
                raise ReviewError("invalid_hunk_count")
        elif line.startswith("--- "):
            old_header = True
        elif line.startswith("+++ "):
            if not old_header or line not in {f"+++ b/{path}", "+++ /dev/null"}:
                raise ReviewError("diff_header_mismatch")
            header_seen = True
            if line == "+++ /dev/null":
                unsupported.add(path)
        elif line.startswith("@@"):
            match = HUNK.fullmatch(line)
            if match is None or not header_seen:
                raise ReviewError("invalid_hunk_header")
            old_left = int(match[2] or 1)
            new_line, new_left = int(match[3]), int(match[4] or 1)
            if new_line < last_end or old_left + new_left > 40000:
                raise ReviewError("overlapping_or_large_hunk")
            last_end = new_line + new_left
            seen_hunk = True
        elif line.startswith(
            (
                "Binary files ",
                "GIT binary patch",
                "new file mode 120000",
                "new file mode 160000",
                "old mode 120000",
                "old mode 160000",
            )
        ):
            unsupported.add(path)
            binary_body = line.startswith(("Binary files ", "GIT binary patch"))
        elif line.startswith(
            (
                "index ",
                "new file mode ",
                "deleted file mode ",
                "old mode ",
                "new mode ",
                "similarity index ",
                "rename from ",
                "rename to ",
            )
        ):
            if line == "similarity index 100%":
                unsupported.add(path)
            if line.startswith(("new mode 120000", "new mode 160000")):
                unsupported.add(path)
        else:
            raise ReviewError("unexpected_diff_line")
    if old_left or new_left or (path is not None and not seen_hunk and path not in unsupported):
        raise ReviewError("incomplete_diff")
    if sum(map(len, changes.values())) > limits.max_changed_lines:
        raise ReviewError("changed_line_limit")
    selected: list[SelectedFile] = []
    skipped: dict[str, int] = {}
    for path in sorted(changes):
        source = sources.get(path)
        reason = None
        if path in unsupported or not changes[path]:
            reason = "unsupported_or_deleted"
        elif not path.endswith(".py"):
            reason = "unsupported_type"
        elif any(fnmatch.fnmatchcase(path, pattern) for pattern in limits.exclusions):
            reason = "excluded"
        elif source is None:
            reason = "missing_content"
        elif source.kind != "file" or "\x00" in source.content:
            reason = "unsafe_file_type"
        elif len(source.content.encode()) > limits.max_file_bytes:
            reason = "file_size_limit"
        elif len(selected) >= limits.max_files:
            reason = "file_count_limit"
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        assert source is not None
        content_lines = source.content.splitlines()
        if any(
            n < 1 or n > len(content_lines) or content_lines[n - 1] != text
            for n, text in expected[path].items()
        ):
            raise ReviewError("snapshot_diff_mismatch")
        selected.append(
            SelectedFile(
                path=path, content=source.content, changed_lines=tuple(sorted(changes[path]))
            )
        )
    return tuple(selected), Coverage(
        selected_files=len(selected),
        skipped=skipped,
        changed_lines=sum(len(f.changed_lines) for f in selected),
    )
