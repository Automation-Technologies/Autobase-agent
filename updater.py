import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Set, Tuple


class UpdaterError(RuntimeError):
    pass


def _configure_stdio_utf8() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    sys.stderr.reconfigure(encoding="utf-8", errors="strict")


@dataclass(frozen=True)
class UpdaterConfig:
    github_repo: str
    version_file: Path
    protected_root_dirs: Set[str]
    protected_root_files: Set[str]
    wipe_dirs: Set[str]
    user_agent: str
    latest_release_timeout_seconds: float
    download_timeout_seconds: float


class Version:
    __slots__ = ("major", "minor", "patch", "raw")

    def __init__(self, raw: str) -> None:
        if raw is None:
            raise UpdaterError("Версия не задана.")
        raw_value = raw.strip()
        if raw_value == "":
            raise UpdaterError("Версия пустая строка.")

        if not raw_value.startswith("v"):
            raise UpdaterError(f"Ожидался тег формата vX.Y.Z, получено: {raw_value!r}")
        core = raw_value[1:]

        parts = core.split(".")
        if len(parts) != 3:
            raise UpdaterError(f"Ожидался тег формата vX.Y.Z, получено: {raw_value!r}")

        try:
            major = int(parts[0])
            minor = int(parts[1])
            patch = int(parts[2])
        except ValueError as exc:
            raise UpdaterError(f"Ожидались числа в теге версии, получено: {raw_value!r}") from exc

        if major < 0 or minor < 0 or patch < 0:
            raise UpdaterError(f"Компоненты версии не могут быть отрицательными: {raw_value!r}")

        self.major = major
        self.minor = minor
        self.patch = patch
        self.raw = raw_value

    def __lt__(self, other: "Version") -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return False
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __str__(self) -> str:
        return self.raw

    def to_tag_string(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    def to_local_string(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"


class GitHubReleaseClient:
    def __init__(self, config: UpdaterConfig) -> None:
        self._config = config

    def get_latest_release(self) -> Tuple[Version, str]:
        url = f"https://api.github.com/repos/{self._config.github_repo}/releases/latest"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self._config.user_agent,
                "Accept": "application/vnd.github+json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._config.latest_release_timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise UpdaterError(f"Ошибка запроса latest release: {exc}") from exc

        tag_name = data.get("tag_name")
        zip_url = data.get("zipball_url")

        if not isinstance(tag_name, str) or tag_name.strip() == "":
            raise UpdaterError("GitHub API не вернул корректный tag_name.")
        if not isinstance(zip_url, str) or zip_url.strip() == "":
            raise UpdaterError("GitHub API не вернул корректный zipball_url.")

        return Version(tag_name), zip_url


class FileSystemUpdater:
    def __init__(self, config: UpdaterConfig, project_root: Path) -> None:
        self._config = config
        self._project_root = project_root

    def _wipe_dirs(self) -> None:
        for name in sorted(self._config.wipe_dirs):
            path = self._project_root / name
            if path.exists():
                shutil.rmtree(path)

    def _iter_source_files(self, extracted_root: Path) -> Iterable[Tuple[Path, Path]]:
        for root, dirs, files in os.walk(extracted_root):
            root_path = Path(root)
            rel_dir = root_path.relative_to(extracted_root)

            if rel_dir == Path("."):
                dirs[:] = [d for d in dirs if d not in self._config.protected_root_dirs]

            for file_name in files:
                if rel_dir == Path(".") and file_name in self._config.protected_root_files:
                    dest_file = self._project_root / file_name
                    if dest_file.exists():
                        continue

                src_file = root_path / file_name
                dest_file = self._project_root / rel_dir / file_name if rel_dir != Path(".") else self._project_root / file_name
                yield src_file, dest_file

    def apply_zip_update(self, zip_path: Path) -> None:
        if not zip_path.exists():
            raise UpdaterError(f"ZIP файл не найден: {str(zip_path)}")

        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            children = list(temp_dir.iterdir())
            if len(children) != 1 or not children[0].is_dir():
                raise UpdaterError("Непредвиденная структура ZIP (ожидалась одна корневая папка).")

            extracted_root = children[0]

            self._wipe_dirs()

            for src_file, dest_file in self._iter_source_files(extracted_root):
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dest_file)


class Updater:
    def __init__(self, config: UpdaterConfig, project_root: Path) -> None:
        self._config = config
        self._project_root = project_root
        self._github = GitHubReleaseClient(config)
        self._fs = FileSystemUpdater(config, project_root)

    def _read_local_version(self) -> Version:
        version_path = self._project_root / self._config.version_file
        if not version_path.exists():
            raise UpdaterError(
                f"Файл версии не найден: {str(version_path)}. "
                f"Создай {self._config.version_file.name} с содержимым вида v1.0.0"
            )
        raw = version_path.read_text(encoding="utf-8").strip()
        return Version(raw)

    def _write_local_version(self, version: Version) -> None:
        version_path = self._project_root / self._config.version_file
        version_path.write_text(version.to_local_string(), encoding="utf-8")

    def _download_zip(self, zip_url: str) -> Path:
        request = urllib.request.Request(
            zip_url,
            headers={"User-Agent": self._config.user_agent},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._config.download_timeout_seconds) as response:
                content = response.read()
        except Exception as exc:
            raise UpdaterError(f"Ошибка скачивания ZIP: {exc}") from exc

        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        try:
            tmp_file.write(content)
            tmp_file.flush()
        finally:
            tmp_file.close()
        return Path(tmp_file.name)

    def run(self) -> int:
        print("=== Updater: проверка обновлений ===")
        local_version = self._read_local_version()
        latest_version, zip_url = self._github.get_latest_release()

        if latest_version == local_version:
            print(f"[Updater] Актуально: {local_version}")
            return 0

        if latest_version < local_version:
            raise UpdaterError(f"Локальная версия новее релиза: local={local_version}, latest={latest_version}")

        print(f"[Updater] Найдено обновление: {local_version} -> {latest_version}")
        zip_path: Optional[Path] = None
        try:
            print("[Updater] Скачивание релиза...")
            zip_path = self._download_zip(zip_url)

            print("[Updater] Применение обновления...")
            self._fs.apply_zip_update(zip_path)

            self._write_local_version(latest_version)
            print(f"[Updater] Успешно обновлено до {latest_version}")
            return 0
        finally:
            if zip_path is not None and zip_path.exists():
                try:
                    zip_path.unlink()
                except Exception:
                    pass


def _build_config() -> UpdaterConfig:
    github_repo = "Automation-Technologies/TA-agent"

    return UpdaterConfig(
        github_repo=github_repo,
        version_file=Path("version.txt"),
        protected_root_dirs={"maFiles", "logs", "config"},
        protected_root_files={"config.json", ".env", "security.salt"},
        wipe_dirs={"core", "steampy", "__pycache__"},
        user_agent="TA-Autobase-Agent-Updater",
        latest_release_timeout_seconds=10.0,
        download_timeout_seconds=30.0,
    )


def main() -> int:
    try:
        _configure_stdio_utf8()
        config = _build_config()
        project_root = Path(__file__).resolve().parent
        return Updater(config, project_root).run()
    except UpdaterError as exc:
        print(f"[Updater] Ошибка: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
