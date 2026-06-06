import subprocess
from pathlib import Path


def test_tracked_source_does_not_contain_legacy_product_name_variants():
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    tracked_files = [path for path in result.stdout.split(b"\0") if path]
    blocked_patterns = (
        b"clinic" + b"flow",
        b"clinic" + b"-" + b"flow",
        b"clinic" + b"_" + b"flow",
        b"clinic" + b" " + b"flow",
    )

    matches = []
    for relative_path in tracked_files:
        path = repo_root / relative_path.decode()
        data = path.read_bytes().lower()
        if any(pattern in data for pattern in blocked_patterns):
            matches.append(str(path.relative_to(repo_root)))

    assert matches == []
