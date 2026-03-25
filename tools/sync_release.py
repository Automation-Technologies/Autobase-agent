import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Set, Tuple


class SyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class SyncConfig:
    source_root: Path
    dest_root: Path
    include_items: Tuple[str, ...]


class ReleaseSync:
    def __init__(self, config: SyncConfig) -> None:
        self._config = config

    def _validate(self) -> None:
        if not self._config.source_root.exists():
            raise SyncError(f"Source не найден: {self._config.source_root}")
        if not self._config.source_root.is_dir():
            raise SyncError(f"Source не папка: {self._config.source_root}")
        if not self._config.dest_root.exists():
            raise SyncError(f"Dest не найден: {self._config.dest_root}")
        if not self._config.dest_root.is_dir():
            raise SyncError(f"Dest не папка: {self._config.dest_root}")

    def _iter_children(self, root: Path) -> Iterable[Path]:
        for p in root.iterdir():
            yield p

    def _wipe_dest(self) -> None:
        for child in self._iter_children(self._config.dest_root):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    def _copy_item(self, src: Path, dst: Path) -> None:
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def run(self) -> None:
        self._validate()
        self._wipe_dest()

        for name in self._config.include_items:
            src_item = self._config.source_root / name
            if not src_item.exists():
                raise SyncError(f"В source отсутствует обязательный элемент: {name}")
            self._copy_item(src_item, self._config.dest_root / name)

        required = ["start.bat", "launcher.py", "version.txt", "python_portable"]
        missing = []
        for item in required:
            if not (self._config.dest_root / item).exists():
                missing.append(item)
        if missing:
            raise SyncError(f"После синка отсутствуют: {', '.join(missing)}")


def main() -> int:
    source_root = Path(r"C:\Users\Victor Golovenko\Desktop\TA_Autobase_bot_agent")
    dest_root = Path(r"C:\Users\Victor Golovenko\Desktop\TA_Agent_Release")

    config = SyncConfig(
        source_root=source_root,
        dest_root=dest_root,
        include_items=(
            "start.bat",
            "launcher.py",
            "main.py",
            "updater.py",
            "version.txt",
            "python_portable",
            "assets",
            "core",
            "gui",
            "steampy",
        ),
    )

    try:
        ReleaseSync(config).run()
        print("[sync_release] OK")
        return 0
    except SyncError as exc:
        print(f"[sync_release] ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
