import datetime as dt
from io import IOBase, BytesIO, StringIO
from pathlib import Path
from typing import Any, Literal, Sequence

import numpy as np
import pandas as pd
from hostess.aws.s3 import Bucket
from botocore.exceptions import ClientError


class MockBucket(Bucket):  # type:ignore[misc] # until hostess is typed
    """
    Mock S3 bucket base class, for testing.  The constructor rejects
    the `client`, `resource`, `session`, and `config` arguments.
    The methods throw plausible S3 failure exceptions or return
    nothing.
    """
    client: None
    resource: None
    session: None
    config: None
    n_threads: int
    name: str

    def __init__(
        self,
        bucket_name: str,
        *,
        client: Any = None,
        resource: Any = None,
        session: Any = None,
        config: Any = None,
        n_threads: int = 4
    ):
        # intentionally does not call Bucket.__init__

        if client is not None:
            raise ValueError("MockBucket cannot use a client")
        if resource is not None:
            raise ValueError("MockBucket cannot use a resource")
        if session is not None:
            raise ValueError("MockBucket cannot use a session")
        if config is not None:
            raise ValueError("MockBucket cannot use a config")

        self.client = None
        self.resource = None
        self.session = None
        self.name = bucket_name
        self.config = None
        self.n_threads = n_threads

    def __str__(self) -> str:
        return f"s3 bucket {self.name} (mock: {type(self).__name__})"

    def __repr__(self) -> str:
        return str(self)

    @property
    def _buckethead(self) -> dict[str, str]:
        return {}

    @property
    def tags(self) -> dict[str, str]:
        return {}

    @property
    def bucket_type(self) -> str:
        return "general"

    @classmethod
    def _not_implemented_error(cls, method: str) -> ClientError:
        return ClientError(
            { "Error": {
                "Code": 400,
                "Message": f"Not implemented by {cls.__name__}"
            } },
            f"'{method}'",
        )

    def _not_found_error(self, method: str, key: str) -> ClientError:
        return ClientError(
            { "Error": {
                "Code": 404,
                "Message": f"Key {key} does not exist"
            } },
            f"'{method}'",
        )

    def _exc_error(self, method: str, exc: Exception) -> ClientError:
        return ClientError(
            { "Error": {
                "Code": 400,
                "Message": str(exc)
            } },
            f"'{method}'",
        )

    def set_tags(self, *, replace_all: bool = False, **tags: str) -> Any:
        raise self._not_implemented_error("set_tags")

    @classmethod
    def create(
        cls,
        name: str,
        client: Any = None,
        session: Any = None,
        *,
        bucket_type: str = "general",
        az: str | int | None = None,
        tags: dict[str, str] | None = None,
        bucket_config: Any = None,
        **bucket_kwargs: Any
    ) -> Any:
        raise cls._not_implemented_error("create")

    def delete(self) -> None:
        raise self._not_implemented_error("delete")

    def update_contents(
        self,
        prefix: str | None = None,
        *,
        cache: Any = None,
        fetch_owner: bool = False
    ) -> Any:
        raise self._not_implemented_error("update_contents")

    def chunk_putter_factory(
        self,
        key: str,
        *,
        upload_threads: int | None = 4,
        download_threads: int | None = None,
        verbose: bool = False,
    ) -> Any:
        raise self._not_implemented_error("chunk_putter_factory")

    def df(self) -> Any:
        raise self._not_implemented_error("df")

    def put_stream(
        self,
        obj: Any,
        key: str,
        *,
        config: Any = None,
        upload_threads: int | None = 4,
        verbose: bool = False,
        explicit_length: int | None = None,
        chunksize: int | None = None,
    ) -> Any:
        raise self._not_implemented_error("put_stream")

    def freeze(
        self,
        key: Any,
        storage_class: str = "DEEP_ARCHIVE",
    ) -> Any:
        raise self._not_implemented_error("freeze")

    def restore(
        self,
        key: str | Sequence[str],
        tier: Literal["Expedited", "Standard", "Bulk"] = "Bulk",
        days: int = 5,
    ) -> Any:
        raise self._not_implemented_error("restore")

    def put(
        self,
        obj: Any = b"",
        key: str | Sequence[str] | None = None,
        *,
        literal_str: bool = False,
        config: Any = None,
        **extra_args: str
    ) -> Any:
        raise self._not_implemented_error("put")

    def get(
        self,
        key: str | Sequence[str],
        destination: Any = None,
        config: Any = None,
        start_byte: int | None = None,
        end_byte: int | None = None,
        **extra_args: str
    ) -> Any:
        raise self._not_implemented_error("get")

    def read(
        self,
        key: str,
        mode: Literal["r", "rb"] = "r",
        *,
        return_buffer: bool = False,
        start_byte: int | None = None,
        end_byte: int | None = None
    ) -> Any:
        raise self._not_implemented_error("read")

    def cp(
        self,
        source: str | Sequence[str],
        destination: str | Sequence[str | None] | None = None,
        destination_bucket: str | None = None,
        config: Any = None,
        **extra_args: str
    ) -> Any:
        raise self._not_implemented_error("cp")

    def append(
        self,
        obj: Any,
        key: str,
        *,
        literal_str: bool = False,
        offset: int | None = None
    ) -> None:
        raise self._not_implemented_error("append")

    def head(
        self, key: str | Sequence[str]
    ) -> dict[str, str] | list[dict[str, str] | Exception]:
        raise self._not_implemented_error("head")

    def tail(
        self,
        key: str,
        destination: Any,
        *,
        start_pos: int | None = None,
        poll: float = 1,
        text_mode: bool = True,
        permit_missing: bool = False
    ) -> Any:
        raise self._not_implemented_error("tail")

    def ls(
        self,
        prefix: str | None = None,
        *,
        recursive: bool = False,
        formatting: Literal["simple", "contents", "df", "raw"] = "simple",
        cache: Any = None,
        start_after: str | None = None,
        cache_only: bool = False,
        fetch_owner: bool = False
    ) -> Any:
        raise self._not_implemented_error("ls")

    def rm(self, key: str) -> Any:
        raise self._not_implemented_error("rm")

    def ls_multipart(self) -> Any:
        raise self._not_implemented_error("ls_multipart")

    def create_multipart_upload(self, key: str) -> Any:
        raise self._not_implemented_error("create_multipart_upload")

    def abort_multipart_upload(self, multipart: Any) -> Any:
        raise self._not_implemented_error("abort_multipart_upload")

    def complete_multipart_upload(
        self,
        multipart: Any,
        parts: Any,
    ) -> Any:
        raise self._not_implemented_error("complete_multipart_upload")


class FakeReadOnlyDataBucket(MockBucket):
    """
    Mock S3 bucket for testing S3Reader.  Implements just the subset of
    the hostess.aws.s3.Bucket API that is used by S3Reader.  The bucket
    name is ignored.  File names of the form "{dtype}-{length}",
    where {dtype} is a NumPy scalar dtype code and {length} is a
    decimal number that is a multiple of the size of {dtype}, will
    contain exactly {length} bytes of data, consisting of sequential
    values of {dtype}; all other filenames are reported as nonexistent.
    """
    _files: dict[str, bytes]

    def __init__(
        self,
        bucket_name: str,
        client: Any = None,
        resource: Any = None,
        session: Any = None,
        config: Any = None,
        n_threads: int = 4
    ):
        super().__init__(
            bucket_name,
            client=client,
            resource=resource,
            session=session,
            config=config,
            n_threads=n_threads,
        )
        self._files = {}

    def get_test_file(self, key: str) -> bytes:
        data = self._files.get(key)
        if data is not None:
            return data

        try:
            dtcode, _, lengthcode = key.partition("-")
            dt = np.dtype(dtcode)
            length = int(lengthcode, base=10)

            nelem, leftover = divmod(length, dt.itemsize)
            if leftover:
                raise ValueError(f"{length} is not a multiple of {dt.itemsize}")

            arr = np.linspace(0, nelem, num=nelem, endpoint=False, dtype=dt)
            data = arr.tobytes()
            self._files[key] = data
            return data

        except Exception as e:
            raise self._exc_error(f"get_test_file({key!r})", e) from e

    # methods actually used by S3Reader
    def head(
        self,
        key: str | Sequence[str],
    ) -> dict[str, str] | list[dict[str, str] | Exception]:
        if not isinstance(key, str):
            raise self._not_implemented_error("multiple-file head")

        data = self.get_test_file(key)
        return { "ContentLength": str(len(data)) }

    def get(
        self,
        key: str | Sequence[str],
        destination: (
            str | Path | IOBase | None | Sequence[str | Path | IOBase | None]
        ) = None,
        config: Any = None,
        start_byte: int | None = None,
        end_byte: int | None = None,
        **extra_args: str
    ) -> str | Path | IOBase | list[str | Path | IOBase | None]:
        if not isinstance(key, str):
            raise self._not_implemented_error("multiple-file get")
        if destination is None:
            destination = BytesIO()
        elif not isinstance(destination, IOBase):
            raise self._not_implemented_error(
                f"get to {type(destination).__name__}"
            )
        if config is not None:
            raise self._not_implemented_error("get with config")
        if extra_args:
            raise self._not_implemented_error("get with extra args")

        data = self.get_test_file(key)

        if start_byte is None:
            start_byte = 0
        if end_byte is None:
            end_byte = len(data)

        destination.seek(0)  # yes, hostess really does this
        destination.write(data[start_byte : (end_byte + 1)])
        return destination


class FakeBucketRegistry:
    """Small registry used by FakeMutableBucket for S3-to-S3 copies."""

    def __init__(self) -> None:
        self.buckets: dict[str, FakeMutableBucket] = {}

    def add(self, bucket: "FakeMutableBucket") -> "FakeMutableBucket":
        self.buckets[bucket.name] = bucket
        return bucket

    def make(self, name: str, **kwargs: Any) -> "FakeMutableBucket":
        return FakeMutableBucket(name, registry=self, **kwargs)

    def get_or_make(self, name: str) -> "FakeMutableBucket":
        if name in self:
            return self[name]
        return self.make(name)

    def __contains__(self, name: str) -> bool:
        return name in self.buckets

    def __getitem__(self, name: str) -> "FakeMutableBucket":
        return self.buckets[name]


class FakeMutableBucket(MockBucket):
    """
    Minimal mutable in-memory Bucket double for upload client / validation
    server tests.
    """

    def __init__(
        self,
        bucket_name: str,
        *,
        registry: FakeBucketRegistry | None = None,
        files: dict[str, bytes | str] | None = None,
        client: Any = None,
        resource: Any = None,
        session: Any = None,
        config: Any = None,
        n_threads: int = 4,
    ):
        super().__init__(
            bucket_name,
            client=client,
            resource=resource,
            session=session,
            config=config,
            n_threads=n_threads,
        )
        self.registry = registry
        self.objects: dict[str, bytes] = {}
        self.last_modified: dict[str, dt.datetime] = {}
        self.object_metadata: dict[str, dict[str, Any]] = {}
        self.calls: dict[str, list[dict[str, Any]]] = {
            "put": [],
            "append": [],
            "get": [],
            "read": [],
            "ls": [],
            "df": [],
            "cp": [],
            "rm": [],
            "head": [],
        }
        if registry is not None:
            registry.add(self)
        for key, value in (files or {}).items():
            self._set_object(key, self._bytes(value, literal_str=True))

    @staticmethod
    def _utcnow() -> dt.datetime:
        return dt.datetime.now(dt.UTC)

    @staticmethod
    def _reject_sequence(value: Any, method: str) -> None:
        if not isinstance(value, (str, bytes, Path)) and isinstance(
            value, Sequence
        ):
            raise MockBucket._not_implemented_error(f"multiple-key {method}")

    @staticmethod
    def _bytes(obj: Any, *, literal_str: bool = False) -> bytes:
        if obj is None:
            return b""
        if isinstance(obj, bytes):
            return obj
        if isinstance(obj, Path):
            return obj.read_bytes()
        if isinstance(obj, str):
            if literal_str is True:
                return obj.encode("utf-8")
            return Path(obj).read_bytes()
        if hasattr(obj, "read"):
            data = obj.read()
            if isinstance(data, str):
                return data.encode("utf-8")
            if isinstance(data, bytes):
                return data
            raise TypeError(f"Cannot put data read as {type(data)}")
        raise TypeError(f"Cannot put object of type {type(obj)}")

    def _set_object(
        self,
        key: str,
        data: bytes,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.objects[key] = data
        self.last_modified[key] = self._utcnow()
        self.object_metadata[key] = dict(metadata or {})

    def _get_object(self, key: str, method: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError as exc:
            raise self._not_found_error(method, key) from exc

    @staticmethod
    def _slice(
        data: bytes, start_byte: int | None, end_byte: int | None
    ) -> bytes:
        start = 0 if start_byte is None else start_byte
        end = len(data) - 1 if end_byte is None else end_byte
        if start < 0:
            start = len(data) + start
        if end < 0:
            end = len(data) + end
        return data[start : end + 1]

    def _contents_record(self, key: str) -> dict[str, Any]:
        return {
            "Key": key,
            "Size": len(self.objects[key]),
            "LastModified": self.last_modified[key],
        }

    def put(
        self,
        obj: Any = b"",
        key: str | Sequence[str] | None = None,
        *,
        literal_str: bool = False,
        config: Any = None,
        checksum: str | None = None,
        **extra_args: Any,
    ) -> None:
        self._reject_sequence(key, "put")
        if key is None:
            key = str(obj)[:1024]
        if not isinstance(key, str):
            raise TypeError(f"key must be str, not {type(key)}")
        if config is not None:
            raise self._not_implemented_error("put with config")
        data = self._bytes(obj, literal_str=literal_str)
        metadata = dict(extra_args)
        if checksum is not None:
            metadata["checksum"] = checksum
        self._set_object(key, data, metadata=metadata)
        self.calls["put"].append(
            {
                "key": key,
                "literal_str": literal_str,
                "checksum": checksum,
                "extra_args": dict(extra_args),
                "size": len(data),
            }
        )

    def append(
        self,
        obj: Any,
        key: str,
        *,
        literal_str: bool = False,
        offset: int | None = None,
    ) -> None:
        data = self._bytes(obj, literal_str=literal_str)
        existing = self.objects.get(key, b"")
        if offset in (None, 0):
            offset = len(existing)
        if offset != len(existing):
            raise self._not_implemented_error("append with non-tail offset")
        self._set_object(key, existing + data)
        self.calls["append"].append(
            {
                "key": key,
                "literal_str": literal_str,
                "offset": offset,
                "size": len(data),
            }
        )

    def get(
        self,
        key: str | Sequence[str],
        destination: Any = None,
        config: Any = None,
        start_byte: int | None = None,
        end_byte: int | None = None,
        **extra_args: Any,
    ) -> Any:
        self._reject_sequence(key, "get")
        if not isinstance(key, str):
            raise TypeError(f"key must be str, not {type(key)}")
        if config is not None:
            raise self._not_implemented_error("get with config")
        if extra_args:
            raise self._not_implemented_error("get with extra args")
        data = self._slice(
            self._get_object(key, "get"), start_byte, end_byte
        )
        self.calls["get"].append(
            {
                "key": key,
                "destination": destination,
                "start_byte": start_byte,
                "end_byte": end_byte,
            }
        )
        if destination is None:
            destination = BytesIO()
        if isinstance(destination, (str, Path)):
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return path
        if not isinstance(destination, IOBase):
            raise self._not_implemented_error(
                f"get to {type(destination).__name__}"
            )
        destination.seek(0)
        destination.write(data)
        destination.seek(0)
        return destination

    def read(
        self,
        key: str,
        mode: Literal["r", "rb"] = "r",
        *,
        return_buffer: bool = False,
        start_byte: int | None = None,
        end_byte: int | None = None,
    ) -> bytes | str | BytesIO | StringIO:
        data = self._slice(
            self._get_object(key, "read"), start_byte, end_byte
        )
        self.calls["read"].append(
            {
                "key": key,
                "mode": mode,
                "return_buffer": return_buffer,
                "start_byte": start_byte,
                "end_byte": end_byte,
            }
        )
        if mode == "rb":
            if return_buffer is True:
                return BytesIO(data)
            return data
        if mode != "r":
            raise ValueError("mode must be 'r' or 'rb'")
        text = data.decode("utf-8")
        if return_buffer is True:
            return StringIO(text)
        return text

    def ls(
        self,
        prefix: str | None = None,
        *,
        recursive: bool = False,
        formatting: Literal["simple", "contents", "df", "raw"] = "simple",
        cache: Any = None,
        start_after: str | None = None,
        cache_only: bool = False,
        fetch_owner: bool = False,
    ) -> tuple[str, ...] | tuple[dict[str, Any], ...] | pd.DataFrame | dict[str, Any]:
        if cache is not None or cache_only is True or fetch_owner is True:
            raise self._not_implemented_error(
                "ls with cache/cache_only/fetch_owner"
            )
        prefix = "" if prefix is None else prefix
        keys = sorted(key for key in self.objects if key.startswith(prefix))
        if start_after is not None:
            keys = [key for key in keys if key > start_after]
        records = tuple(self._contents_record(key) for key in keys)
        self.calls["ls"].append(
            {
                "prefix": prefix,
                "recursive": recursive,
                "formatting": formatting,
                "start_after": start_after,
            }
        )
        if formatting == "simple":
            return tuple(keys)
        if formatting == "contents":
            return records
        if formatting == "df":
            return pd.DataFrame(
                records, columns=["Key", "Size", "LastModified"]
            )
        if formatting == "raw":
            return {"Contents": list(records)}
        raise ValueError(f"Unknown ls formatting {formatting!r}")

    def df(self) -> pd.DataFrame:
        self.calls["df"].append({})
        return self.ls(formatting="df")

    def rm(self, key: str) -> None:
        self.objects.pop(key, None)
        self.last_modified.pop(key, None)
        self.object_metadata.pop(key, None)
        self.calls["rm"].append({"key": key})

    def cp(
        self,
        source: str | Sequence[str],
        destination: str | Sequence[str | None] | None = None,
        destination_bucket: str | None = None,
        config: Any = None,
        **extra_args: Any,
    ) -> str:
        self._reject_sequence(source, "cp")
        self._reject_sequence(destination, "cp")
        if not isinstance(source, str):
            raise TypeError(f"source must be str, not {type(source)}")
        if destination is None:
            destination = source
        if not isinstance(destination, str):
            raise TypeError(
                f"destination must be str, not {type(destination)}"
            )
        if config is not None:
            raise self._not_implemented_error("cp with config")
        if extra_args:
            raise self._not_implemented_error("cp with extra args")
        target_name = (
            self.name if destination_bucket is None else destination_bucket
        )
        if self.registry is None:
            if target_name != self.name:
                raise KeyError(
                    f"No registry available for bucket {target_name!r}"
                )
            target = self
        else:
            target = self.registry[target_name]
        data = self._get_object(source, "cp")
        target._set_object(
            destination,
            data,
            metadata=dict(self.object_metadata.get(source, {})),
        )
        self.calls["cp"].append(
            {
                "source": source,
                "destination": destination,
                "destination_bucket": target_name,
            }
        )
        return f"s3://{target_name}:{destination}"

    def head(
        self, key: str | Sequence[str]
    ) -> dict[str, Any] | list[dict[str, Any] | Exception]:
        self._reject_sequence(key, "head")
        if not isinstance(key, str):
            raise TypeError(f"key must be str, not {type(key)}")
        data = self._get_object(key, "head")
        self.calls["head"].append({"key": key})
        return {
            "ContentLength": len(data),
            "LastModified": self.last_modified[key].isoformat(),
            "Metadata": dict(self.object_metadata.get(key, {})),
        }
