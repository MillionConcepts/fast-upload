from astropy.io import fits

from hostess.aws.s3 import Bucket


def fitsopen_generic(
    key: str, bucket: Bucket | str | None = None
) -> fits.HDUList:
    """
    Open an S3 object or local file as an HDUList. Note that unlike the ASDF
    and Parquet versions, this does not accept a `blocksize` argument. This is
    because it relies on astropy's FITS S3 behaviors, which are already
    somewhat 'smart'.

    Args:
        key: path or S3 key
        bucket: Bucket object or bucket name if this is an S3 object; None if
            a local file
    Returns:
        an HDUList object created from `key`
    """
    bucket = bucket.name if isinstance(bucket, Bucket) else bucket
    if bucket is not None:
        return fits.open(f's3://{bucket}/{key}')
    return fits.open(key)
