"""
Workarounds for various gaps in the Python language and in its
type annotations.
"""

import os

from pathlib import Path
from typing import Any, Callable, Generic, Iterator, Protocol, Self, TypeVar


class SupportsClose(Protocol):
    def close(self) -> None: ...


T = TypeVar("T")
RT = TypeVar("RT")
SC = TypeVar("SC", bound=SupportsClose)


class classproperty(Generic[T, RT]):
    """
    Decorator which converts a method into a class property;
    this _ought_ to be spelled

        class Thing:
             @property @classmethod
             def prop(cls):
                 return "whatever"

    but that doesn't work for reasons too tedious to get into
    (see <https://github.com/python/cpython/issues/89519> for gory details)
    This is the recommended workaround.  Note that only read-only
    properties can be supported (that's one of the tedious reasons).
    """

    def __init__(self, func: Callable[[type[T]], RT]) -> None:
        # For using `help(...)` on instances
        self.__doc__ = func.__doc__
        self.__module__ = func.__module__
        self.__name__ = func.__name__
        self.__qualname__ = func.__qualname__
        # Consistent use of __wrapped__ for wrapping functions.
        self.__wrapped__: Callable[[type[T]], RT] = func

    def __set_name__(self, owner: type[T], name: str) -> None:
        # Update based on class context.
        self.__module__ = owner.__module__
        self.__name__ = name
        self.__qualname__ = owner.__qualname__ + "." + name

    def __get__(self, instance: T | None, owner: type[T] | None = None) -> RT:
        if owner is not None:
            return self.__wrapped__(owner)
        assert instance is not None
        return self.__wrapped__(type(instance))


class close_or_forget(Generic[SC]):
    """
    Context manager wrapper for any object with a close method, which
    _conditionally_ closes that object on exit from the with-block.

    On entry, returns self.  The wrapped object can be accessed via
    the 'resource' property.  On exit, the wrapped object's close
    method is called UNLESS the forget() method has been called to
    transfer ownership of the wrapped object to the caller.
    """

    _resource: SC | None

    def __init__(self, resource: SC):
        self._resource = resource

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *dontcare: Any) -> None:
        if self._resource is not None:
            self._resource.close()

    @property
    def resource(self) -> SC:
        r = self._resource
        if r is None:
            raise RuntimeError(
                "close_or_forget.resource accessed after forget"
            )
        return r

    def forget(self) -> SC:
        """Shorthand: sets self.resource to None and then returns the
        old value of self.resource."""
        r = self._resource
        if r is None:
            raise RuntimeError("close_or_forget.forget called twice")
        self._resource = None
        return r


class RelPathDirEntry:
    """
    Wraps an os.DirEntry and alters its `path` attribute to be a Path object
    which provides the *relative* pathname from some base directory.

    The base directory itself is accessible via the `base` attribute;
    this is guaranteed to be a resolved absolute path.

    All other documented methods and properties of `os.DirEntry` are available
    with the same semantics as the original.
    """

    __slots__ = ("_inner", "path", "base")

    _inner: os.DirEntry[str]
    path: Path
    base: Path

    def __init__(self, inner: os.DirEntry[str], base: Path, path: Path):
        self._inner = inner
        self.path = path
        self.base = base

    @property
    def name(self) -> str:
        return self._inner.name

    def inode(self) -> int:
        return self._inner.inode()

    def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
        return self._inner.stat(follow_symlinks=follow_symlinks)

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        return self._inner.is_dir(follow_symlinks=follow_symlinks)

    def is_file(self, *, follow_symlinks: bool = True) -> bool:
        return self._inner.is_file(follow_symlinks=follow_symlinks)

    def is_symlink(self) -> bool:
        return self._inner.is_symlink()

    # in 3.12 and higher DirEntry also has an 'is_junction' method, but
    # our minimum Python is still 3.11, so we do not provide that method
    # at all.


def path_walk(root: Path) -> Iterator[RelPathDirEntry]:
    """
    A mash-up of `os.scandir` and `Path.walk` having the best properties
    of both (hopefully).

    Yield RelPathDirEntry objects for each directory entry in the tree
    rooted at `root`.  The base directory for each object will be `root`.

    Does not follow symlinks within `root` under any circumstances;
    you get an entry object for the symlink itself and that's it.

    The directory tree should not be modified while the walk is underway.
    """

    def rec_walk(curdir: Path) -> Iterator[RelPathDirEntry]:
        relbase = curdir.relative_to(base)
        with os.scandir(curdir) as dentries:
            for entry in dentries:
                if entry.name in (".", ".."):
                    continue
                yield RelPathDirEntry(entry, base, relbase / entry.name)
                if entry.is_dir(follow_symlinks=False):
                    yield from rec_walk(curdir / entry.name)

    base = root.resolve()
    return rec_walk(base)
