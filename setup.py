from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import atexit
import tempfile

from setuptools import setup
from setuptools.command.build import build as _build
from setuptools.command.egg_info import egg_info as _egg_info


REPO_ROOT = Path(__file__).parent.resolve()
_TEMP_BUILD_OWNERS: list[tuple[object, object]] = []


def _source_tree_is_writable() -> bool:
    probe = REPO_ROOT / ".setuptools-write-probe"
    try:
        with probe.open("w", encoding="utf-8") as handle:
            handle.write("")
        probe.unlink()
    except OSError:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True


def _temporary_build_dir(kind: str) -> str:
    from hermes_temp import current_temp_authority
    authority = current_temp_authority()
    owner = authority.mkdir(f"setuptools-{kind}")
    _TEMP_BUILD_OWNERS.append((owner, authority))
    return str(owner.path)


def _cleanup_build_dirs() -> None:
    while _TEMP_BUILD_OWNERS:
        owner, authority = _TEMP_BUILD_OWNERS.pop()
        try:
            owner.cleanup()
        finally:
            authority.close()


atexit.register(_cleanup_build_dirs)


def _would_write_under_source(path_value: str | None) -> bool:
    if path_value is None:
        return True
    path = Path(path_value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    try:
        path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return False
    return True


class ReadOnlySourceBuild(_build):
    def finalize_options(self) -> None:
        if (
            not _source_tree_is_writable()
            and _would_write_under_source(self.build_base)
        ):
            self.build_base = _temporary_build_dir("build")
        super().finalize_options()


class ReadOnlySourceEggInfo(_egg_info):
    def finalize_options(self) -> None:
        if (
            not _source_tree_is_writable()
            and _would_write_under_source(self.egg_base)
        ):
            self.egg_base = _temporary_build_dir("egg-info")
        super().finalize_options()


def _data_file_tree(root_name: str) -> list[tuple[str, list[str]]]:
    root = REPO_ROOT / root_name
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(REPO_ROOT)
        grouped[str(rel_path.parent)].append(str(rel_path))
    return sorted(grouped.items())


setup(
    cmdclass={
        "build": ReadOnlySourceBuild,
        "egg_info": ReadOnlySourceEggInfo,
    },
    data_files=[
        *_data_file_tree("skills"),
        *_data_file_tree("optional-skills"),
    ]
)
