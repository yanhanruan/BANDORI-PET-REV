import json
import tarfile
from contextlib import contextmanager
from pathlib import Path


VIRTUAL_SEP = "::"
INDEX_MEMBER = ".bandori_zst_index.json"


def is_virtual_path(path: str) -> bool:
    return VIRTUAL_SEP in str(path)


def make_virtual_path(archive_path: Path | str, member_path: str) -> str:
    return f"{Path(archive_path).resolve()}{VIRTUAL_SEP}{_normalize_member(member_path)}"


def split_virtual_path(path: str) -> tuple[str, str]:
    archive_path, member_path = str(path).split(VIRTUAL_SEP, 1)
    return archive_path, _normalize_member(member_path)


def load_virtual_bytes(path: str) -> bytes:
    archive_path, member_path = split_virtual_path(path)
    with _open_tar_zst(archive_path) as archive:
        for member in archive:
            if not member.isfile() or _normalize_member(member.name) != member_path:
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                break
            return extracted.read()
    raise KeyError(path)


def read_virtual_text(path: str, encoding: str = "utf-8") -> str:
    return load_virtual_bytes(path).decode(encoding)


def load_virtual_json(path: str) -> dict:
    return json.loads(read_virtual_text(path))


def list_archive_files(archive_path: Path | str) -> list[str]:
    files = []
    with _open_tar_zst(str(Path(archive_path).resolve())) as archive:
        members = iter(archive)
        first = next(members, None)
        if first is not None:
            first_name = _normalize_member(first.name)
            if first.isfile() and first_name == INDEX_MEMBER:
                extracted = archive.extractfile(first)
                if extracted is not None:
                    data = json.loads(extracted.read().decode("utf-8"))
                    indexed_files = data.get("files", [])
                    if isinstance(indexed_files, list):
                        return sorted(str(path) for path in indexed_files)
            elif first.isfile():
                files.append(first_name)
        for member in members:
            if member.isfile():
                files.append(_normalize_member(member.name))
    return sorted(files)


@contextmanager
def _open_tar_zst(archive_path: str):
    try:
        import zstandard as zstd
    except ImportError as exc:
        raise RuntimeError("Reading .zst models requires zstandard: pip install zstandard") from exc

    with Path(archive_path).open("rb") as raw_file:
        with zstd.ZstdDecompressor().stream_reader(raw_file) as reader:
            with tarfile.open(fileobj=reader, mode="r|") as archive:
                yield archive


def _normalize_member(path: str) -> str:
    normalized = str(path).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")
