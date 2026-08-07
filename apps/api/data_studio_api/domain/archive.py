from collections import deque
from collections.abc import Iterable, Iterator
from typing import IO, Protocol, cast
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from ..storage import ObjectStorage


class ArchiveFile(Protocol):
    path: str
    size_bytes: int
    storage_object_key: str


class _StreamingZipBuffer:
    def __init__(self) -> None:
        self._chunks: deque[bytes] = deque()
        self._position = 0

    def write(self, data: bytes) -> int:
        chunk = bytes(data)
        self._chunks.append(chunk)
        self._position += len(chunk)
        return len(chunk)

    def tell(self) -> int:
        return self._position

    def flush(self) -> None:
        return None

    def seek(self, offset: int, whence: int = 0) -> int:
        del offset, whence
        raise OSError("The streaming ZIP output is not seekable")

    def drain(self) -> bytes:
        if not self._chunks:
            return b""
        chunk = b"".join(self._chunks)
        self._chunks.clear()
        return chunk


def iter_repository_zip(
    files: Iterable[ArchiveFile],
    storage: ObjectStorage,
) -> Iterator[bytes]:
    """Stream a ZIP containing the immutable source tree without buffering it in memory."""
    output = _StreamingZipBuffer()
    with ZipFile(
        cast(IO[bytes], output),
        mode="w",
        compression=ZIP_STORED,
        allowZip64=True,
    ) as archive:
        for repository_file in files:
            info = ZipInfo(repository_file.path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_STORED
            info.external_attr = 0o100644 << 16
            with archive.open(
                info,
                mode="w",
                force_zip64=repository_file.size_bytes >= 2 * 1024 * 1024 * 1024,
            ) as destination:
                if chunk := output.drain():
                    yield chunk
                for source_chunk in storage.iter_object(repository_file.storage_object_key):
                    destination.write(source_chunk)
                    if chunk := output.drain():
                        yield chunk
            if chunk := output.drain():
                yield chunk
    if chunk := output.drain():
        yield chunk
