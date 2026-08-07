from io import BytesIO
from typing import Any

from data_studio_api.storage import S3RangeReader


class FakeS3Client:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.ranges: list[str] = []

    def head_object(self, **kwargs: Any) -> dict[str, int]:
        del kwargs
        return {"ContentLength": len(self.content)}

    def get_object(self, **kwargs: Any) -> dict[str, BytesIO]:
        range_ = str(kwargs["Range"])
        self.ranges.append(range_)
        start, end = (int(value) for value in range_[6:].split("-"))
        return {"Body": BytesIO(self.content[start : end + 1])}


def test_s3_range_reader_fetches_only_seeked_blocks() -> None:
    client = FakeS3Client(b"0123456789abcdef")
    reader = S3RangeReader(client, "datasets", "train.parquet", block_size=4)
    reader.seek(6)
    output = bytearray(5)

    assert reader.readinto(output) == 5
    assert bytes(output) == b"6789a"
    assert client.ranges == ["bytes=4-7", "bytes=8-11"]
