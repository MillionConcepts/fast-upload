from botocore.exceptions import ClientError
from hostess.aws.s3 import Bucket


def s3_append_write_text(
    bucket: Bucket, key: str, line: str
) -> None:
    """very simple one-shot write"""
    try:
        text = bucket.get(key).read().decode('utf-8')
        bucket.put(f"{text}\n{line}", key, literal_str=True)
    except ClientError:
        # TODO: overly broad. meant to catch file-not-found without extra op
        bucket.put(line, key, literal_str=True)
