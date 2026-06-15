from astropy.io import fits

from hostess.aws.s3 import Bucket


def fitsopen_generic(
    key: str, bucket: Bucket | str | None = None
) -> fits.HDUList:
    """Open an S3 object or local file as an HDUList."""
    bucket = bucket.name if isinstance(bucket, Bucket) else bucket
    if bucket is not None:
        return fits.open(f's3://{bucket}/{key}')
    return fits.open(key)
