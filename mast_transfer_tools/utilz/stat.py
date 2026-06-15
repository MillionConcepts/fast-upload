import stat


def a_filetype(mode: int) -> str:
    """Produce a nice human-readable string describing the file type
    encoded in the 'st_mode' field of os.stat_result.  It will be
    prefixed with an indefinite article: 'a regular file, 'a directory',
    etc.

    This is all alone in its own file because it's only needed for
    diagnostics in unusual circumstances so we want to avoid loading
    it unless we do need it.
    """

    if stat.S_ISCHR(mode):
        return "a character device"
    if stat.S_ISBLK(mode):
        return "a block device"
    if stat.S_ISFIFO(mode):
        return "a named pipe"
    if stat.S_ISSOCK(mode):
        return "a local socket"
    if stat.S_ISDOOR(mode):
        return "a door"
    if stat.S_ISPORT(mode):
        return "an event port"
    if stat.S_ISWHT(mode):
        return "a whited-out name"

    # these are at the end, despite being the three most common cases,
    # because we expect that this function will almost always be
    # called on directory entries that *aren't* one of these.
    if stat.S_ISLNK(mode):
        return "a symbolic link"
    if stat.S_ISDIR(mode):
        return "a directory"
    if stat.S_ISREG(mode):
        return "a regular file"

    return "a strange type of file (mode 0o{:02o}____)".format(
        stat.S_IFMT(mode) >> 12
    )
