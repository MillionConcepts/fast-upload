"""Utility functions for working with numbers."""

import re


SCALE_SUFFIXES = {
    # No suffix means no scaling.
    "":   1,

    # SI (powers of ten) up to the maximum currently defined (10**30).
    # For this application, probably nobody *wants* anything but k, M, or G,
    # but let's be as future proof as we can possibly be.  k is recognized
    # case insensitively because people are often sloppy about that.
    "da": 10,
    "h":  100,
    "k":  1000,
    "K":  1000,
    "M":  1000_000,
    "G":  1000_000_000,
    "T":  1000_000_000_000,
    "P":  1000_000_000_000_000,
    "E":  1000_000_000_000_000_000,
    "Z":  1000_000_000_000_000_000_000,
    "Y":  1000_000_000_000_000_000_000_000,
    "R":  1000_000_000_000_000_000_000_000_000,
    "Q":  1000_000_000_000_000_000_000_000_000_000,

    # IEC (powers of 1024) up to 1024**10.  I wish SI had had the nerve
    # to declare that their prefixes exclusively meant powers of 1024
    # when applied to bytes.  So it goes.  As above, Ki is recognized
    # with either case for the K.
    "ki":  1024,
    "Ki":  1024,
    "Mi":  1048_576,
    "Gi":  1073_741_824,
    "Ti":  1099_511_627_776,
    "Pi":  1125_899_906_842_624,
    "Ei":  1152_921_504_606_846_976,
    "Zi":  1180_591_620_717_411_303_424,
    "Yi":  1208_925_819_614_629_174_706_176,
    "Ri":  1237_940_039_285_380_274_899_124_224,
    "Qi":  1267_650_600_228_229_401_496_703_205_376,
}


def parse_bytes_with_scale(s: str) -> int:
    """Parse a number of bytes, possibly written with a scale suffix
    and/or a trailing B to indicate bytes.  A leading + is acceptable
    (but a leading - is not -- a negative number of bytes does not
    make sense in the contexts of use).  The number is interpreted as
    decimal and may use _ , . ' or whitespace as visual separators.
    """
    m = re.fullmatch(
        r"""(?xu)\A
            \s* (?P<sign> [-−+]?)
            \s* (?P<digits> [0-9',._\s]+?)
            \s* (?P<suffix> [a-zA-Z]*)
            \s* \Z""",
        s,
    )
    if not m:
        raise ValueError(f"invalid number {s!r}")

    sign = m.group("sign")
    if sign not in ("", "+"):
        raise ValueError("may not be negative")

    suffix = m.group("suffix").removesuffix("B")
    if suffix not in SCALE_SUFFIXES:
        # this might be overly pedantic
        if suffix.endswith("b"):
            raise ValueError("cannot scale from bits to bytes")
        raise ValueError("unrecognized scale suffix " + repr(m.group("suffix")))

    digits = int(re.sub(r"[',._\s]+", "", m.group("digits")))

    if digits == 0:
        raise ValueError("may not be zero")

    return digits * SCALE_SUFFIXES[suffix]
