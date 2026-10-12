"""Create a portable source ZIP without local credentials, databases or dependencies."""

import argparse, hashlib, json, os
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "exports",
    "qa",
    "qa-output",
}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".zip",
    ".log",
    ".tsbuildinfo",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", default=str(ROOT.parent / "PULSEIQ_Complete_Project.zip")
    )
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    paths = []
    for directory, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink() or path.suffix in EXCLUDED_SUFFIXES:
                continue
            if name.startswith(".env") and name != ".env.example":
                continue
            if name == "release-manifest.json":
                continue
            paths.append(path)
    manifest = {"project": "PULSEIQ", "version": "2.0.0", "files": {}}
    with ZipFile(output, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(paths):
            relative = path.relative_to(ROOT).as_posix()
            blob = path.read_bytes()
            archive.writestr("PULSEIQ/" + relative, blob)
            manifest["files"][relative] = {
                "bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
        archive.writestr(
            "PULSEIQ/release-manifest.json", json.dumps(manifest, indent=2) + "\n"
        )
    print(
        f"{output}\n{len(paths)} source/assets files; {output.stat().st_size:,} bytes"
    )


if __name__ == "__main__":
    main()
