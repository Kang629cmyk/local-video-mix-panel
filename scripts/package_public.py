from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PUBLIC_DIR = DIST / "local-video-mix-panel"
ZIP_PATH = DIST / "local-video-mix-panel-public.zip"

INCLUDE_FILES = [
    ".gitignore",
    "README.md",
    "requirements.txt",
    "config.yaml",
    "config.example.ini",
    "auto_schedule.example.txt",
    "自動排程輸出.bat",
    "開啟使用者面板.bat",
    "開啟使用者面板.pyw",
]

INCLUDE_DIRS = [
    "panel",
    "scripts",
]

EXCLUDE_NAMES = {
    "__pycache__",
}

EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
}


def clear_public_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def ensure_inside_workspace(path: Path) -> Path:
    resolved = path.resolve()
    root = ROOT.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"Refusing to operate outside workspace: {resolved}") from exc
    return resolved


def copy_tree(src: Path, dst: Path) -> None:
    def ignore(_dir: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            if name in EXCLUDE_NAMES or Path(name).suffix in EXCLUDE_SUFFIXES:
                ignored.add(name)
        return ignored

    shutil.copytree(src, dst, ignore=ignore)


def main() -> None:
    public_dir = ensure_inside_workspace(PUBLIC_DIR)
    zip_path = ensure_inside_workspace(ZIP_PATH)
    dist_dir = ensure_inside_workspace(DIST)

    if public_dir.exists():
        clear_public_dir(public_dir)
    if zip_path.exists():
        zip_path.unlink()

    dist_dir.mkdir(parents=True, exist_ok=True)
    public_dir.mkdir(parents=True, exist_ok=True)

    for rel in INCLUDE_FILES:
        src = ROOT / rel
        if not src.exists():
            raise FileNotFoundError(src)
        dst = public_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    for rel in INCLUDE_DIRS:
        src = ROOT / rel
        if not src.exists():
            raise FileNotFoundError(src)
        copy_tree(src, public_dir / rel)

    shutil.copy2(ROOT / "auto_schedule.example.txt", public_dir / "auto_schedule.txt")

    archive_base = zip_path.with_suffix("")
    shutil.make_archive(str(archive_base), "zip", root_dir=public_dir)

    print(f"PUBLIC_DIR={public_dir}")
    print(f"ZIP_PATH={zip_path}")


if __name__ == "__main__":
    main()
