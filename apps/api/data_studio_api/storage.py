import io
import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO, Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from .config import Settings


class ObjectStorage(Protocol):
    def put_file(self, key: str, source: Path) -> None: ...

    def put_bytes(self, key: str, content: bytes, content_type: str) -> None: ...

    def iter_object(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]: ...

    def open_object(self, key: str) -> BinaryIO: ...

    def has_object(self, key: str) -> bool: ...

    def delete_prefix(self, prefix: str) -> None: ...

    def delete_objects(self, keys: list[str]) -> None: ...


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        resolved = (self.root / key).resolve()
        if self.root not in resolved.parents:
            raise ValueError("Object key escapes the storage root")
        return resolved

    def put_file(self, key: str, source: Path) -> None:
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(source, destination)

    def put_bytes(self, key: str, content: bytes, content_type: str) -> None:
        del content_type
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(content)

    def iter_object(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        with self._resolve(key).open("rb") as handle:
            while chunk := handle.read(chunk_size):
                yield chunk

    def open_object(self, key: str) -> BinaryIO:
        return self._resolve(key).open("rb")

    def has_object(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete_prefix(self, prefix: str) -> None:
        target = self._resolve(prefix.rstrip("/"))
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    def delete_objects(self, keys: list[str]) -> None:
        for key in set(keys):
            target = self._resolve(key)
            if target.is_file():
                target.unlink()
            parent = target.parent
            while parent != self.root and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent


class S3ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        for attempt in range(settings.s3_connect_retries):
            try:
                self.client.head_bucket(Bucket=self.bucket)
                break
            except EndpointConnectionError:
                if attempt == settings.s3_connect_retries - 1:
                    raise
                time.sleep(1)
            except ClientError as exc:
                error_code = str(exc.response.get("Error", {}).get("Code", ""))
                if error_code in {"404", "NoSuchBucket", "NotFound"}:
                    self.client.create_bucket(Bucket=self.bucket)
                    break
                raise

    def put_file(self, key: str, source: Path) -> None:
        self.client.upload_file(str(source), self.bucket, key)

    def put_bytes(self, key: str, content: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=content_type)

    def iter_object(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body: BinaryIO = response["Body"]
        while chunk := body.read(chunk_size):
            yield chunk

    def open_object(self, key: str) -> BinaryIO:
        return io.BufferedReader(
            S3RangeReader(self.client, self.bucket, key),
            buffer_size=1024 * 1024,
        )

    def has_object(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def delete_prefix(self, prefix: str) -> None:
        while True:
            response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            objects = [{"Key": item["Key"]} for item in response.get("Contents", [])]
            if not objects:
                break
            self.client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": objects, "Quiet": True},
            )
            if not response.get("IsTruncated"):
                break

    def delete_objects(self, keys: list[str]) -> None:
        unique = sorted(set(keys))
        for offset in range(0, len(unique), 1_000):
            batch = unique[offset : offset + 1_000]
            if batch:
                self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
                )


class S3RangeReader(io.RawIOBase):
    def __init__(
        self,
        client: Any,
        bucket: str,
        key: str,
        block_size: int = 4 * 1024 * 1024,
    ) -> None:
        super().__init__()
        self.client = client
        self.bucket = bucket
        self.key = key
        self.block_size = block_size
        self.size = int(client.head_object(Bucket=bucket, Key=key)["ContentLength"])
        self.position = 0
        self.cache_start = -1
        self.cache = b""

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self.position + offset
        elif whence == io.SEEK_END:
            position = self.size + offset
        else:
            raise ValueError(f"Unsupported seek mode: {whence}")
        if position < 0:
            raise ValueError("Cannot seek before the beginning of an object.")
        self.position = min(position, self.size)
        return self.position

    def _load_block(self) -> None:
        if self.position >= self.size:
            self.cache_start = self.size
            self.cache = b""
            return
        start = (self.position // self.block_size) * self.block_size
        end = min(self.size - 1, start + self.block_size - 1)
        response = self.client.get_object(
            Bucket=self.bucket,
            Key=self.key,
            Range=f"bytes={start}-{end}",
        )
        body = response["Body"]
        try:
            self.cache = body.read()
        finally:
            close = getattr(body, "close", None)
            if close is not None:
                close()
        self.cache_start = start

    def readinto(self, buffer: Any) -> int:
        view = memoryview(buffer).cast("B")
        if not view or self.position >= self.size:
            return 0
        written = 0
        while written < len(view) and self.position < self.size:
            cache_end = self.cache_start + len(self.cache)
            if not (self.cache_start <= self.position < cache_end):
                self._load_block()
                cache_end = self.cache_start + len(self.cache)
                if not self.cache:
                    break
            source_start = self.position - self.cache_start
            count = min(len(view) - written, cache_end - self.position)
            view[written : written + count] = self.cache[source_start : source_start + count]
            written += count
            self.position += count
        return written


def create_storage(settings: Settings) -> ObjectStorage:
    if settings.storage_backend == "s3":
        return S3ObjectStorage(settings)
    return LocalObjectStorage(settings.storage_root)
