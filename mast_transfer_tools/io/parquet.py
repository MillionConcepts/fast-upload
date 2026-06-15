from hostess.aws.s3 import Bucket
from pyarrow import parquet as pq

from mast_transfer_tools.io.s3 import DEFAULT_CHUNK_SIZE, S3Reader


def parquetopen_generic(
    key: str,
    bucket: Bucket | str | None = None,
    blocksize: int = DEFAULT_CHUNK_SIZE,
) -> pq.ParquetFile:
    """Open an S3 object or local file as a ParquetFile."""
    if bucket is None:
        return pq.ParquetFile(key)
    if not isinstance(bucket, Bucket):
        bucket = Bucket(bucket)
    return pq.ParquetFile(S3Reader(bucket, key, chunk_size=blocksize))
