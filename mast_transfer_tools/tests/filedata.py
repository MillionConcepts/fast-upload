"""
Data of a bunch of different kinds of files that get used in tests.
"""

import pytest


from base64 import b64decode


# For each recognized compression format, this is (the base64 encoding of)
# what you get when you ask it to compress an empty file.  This should
# have one entry for each extension in compression.RECOGNIZED_COMPRESSION_EXTS
# (not just SUPPORTED_COMPRESSION_EXTS) and should be kept in the same
# order as that array.
COMPRESSED_FILES_DATA: dict[str, str | bytes] = {
    # gzip
    ".gz": b"H4sIAAAAAAAAAwMAAAAAAAAAAAA=",
    # bzip2
    ".bz2": b"QlpoORdyRThQkAAAAAA=",
    # Lempel-Ziv by itself, focused on fast decompression
    ".lz4": b"BCJNGGRApwAAAAAFXcwC",
    # Lempel-Ziv-Oberhumer, also focused on fast decompression
    ".lzo": b"iUxaTwANChoKEEAgoAlAAQUDAAANAAAAAGlepxAAAAAAACruAu4AAAAA",
    # xz container for LZMA compression
    ".xz": b"/Td6WFoAAATm1rRGAAAAABzfRCEftvN9AQAAAAAEWVo=",
    # Zstandard
    ".zst": b"KLUv/SQAAQAAmenYUQ==",
    # PK-Zip (contents: one empty file with no name)
    ".zip": (
        b"UEsDBBQAAAAAAAAAIQAAAAAAAAAAAAAAAAAAAAAAUEsBAhQDFAAAAAAAAAAhAAAAAAA"
        b"AAAAAAAAAAAAAAAAAAAAAAAAAAIABAAAAAFBLBQYAAAAAAQABAC4AAAAeAAAAAAA="
    ),
    # 7-Zip native format (contents: one empty file named "X")
    ".7z": (
        b"N3q8ryccAARAPWcVAAAAAAAAAAAqAAAAAAAAAJL8ZCkBBQEOAYAPAYAZAgAAEQUAWAA"
        b"AABQKAQAAgD7V3rGdARUGAQAggKSBAAA="
    ),
    # the original bzip, with the patented arithmetic coding that no one
    # wanted to touch
    ".bz": b"QlowOX/////VbJW6AAAAAAA=",
    # alternative, rarely used LZMA-based compression format
    ".lz": b"TFpJUAEMAIP/+///wAAAAAAAAAAAAAAAAAAAACQAAAAAAAAA",
    # legacy container for LZMA compression
    ".lzma": b"XQAAQAD//////////wCD//v//8AAAAA=",
    # WinRAR native format (contents: one empty file named "X")
    ".rar": (
        b"UmFyIRoHAQAzkrXlCgEFBgAFAQGAgABxXpjCFwICgAAGgACkgwIAAAAAAAAAAIAAAQF"
        b"YHXdWUQMFBAA="
    ),
    # legacy Unix compress(1)
    # there were historically a bunch of variations, this is just one of them
    # (the most commonly used); yes it really does come out that short
    ".z": b"H52Q",
}


compressed_exts = frozenset(COMPRESSED_FILES_DATA.keys())


# this should include all our officially supported astro data file
# formats (ASDF, FITS, Parquet) and as many plausibly encountered
# ancillary file formats as practical
UNCOMPRESSED_FILES_DATA: dict[str, str | bytes] = {
    # plain text
    # pangrams
    ".en.txt": "Amazingly, few discotheques provide jukeboxes.\n",
    ".ru.txt": (
        "Разъяренный чтец эгоистично бьёт пятью жердями"
        " шустрого фехтовальщика.\n"
    ),
    # one line from from 古詩十九首 (Nineteen Old Poems)
    ".zh.txt": "青青河畔草，鬱鬱園中柳。盈盈樓上女，皎皎當窗牖。\n",
    # same as previous, converted to UTF-16
    ".zh.u16": (
        b"//5Sl1KXs2xUdUmDDP8xmzGbElctTvNnAjDIdsh2E2oKTnNZDP+Odo52dnWXelZyAjA"
        b"KAA=="
    ),
    # technically text
    ".csv": """\
"class","name","rgb","h","s","l"
"gradient","base03","#002b36",221.86585404374446,99.99999999999162,15.455681880029228
"gradient","base02","#073642",221.03370882612367,93.7573739806417,20.348501160909258
"gradient","base01","#586e75",215.3291469789668,34.73223979464555,44.95657452649872
"gradient","base00","#657b83",217.60572654855332,31.979348356364596,50.18150198015938
"gradient","base0","#839496",201.17732654842686,20.323513039095236,60.075142979771215
"gradient","base1","#93a1a1",192.17705063005866,15.205518520207114,65.17295531706614
"gradient","base2","#eee8d5",73.19665276224539,22.86448821340325,91.99569293770158
"gradient","base3","#fdf6e3",71.33796898586635,76.23143062043535,96.95935383092058
"accent","yellow","#b58900",58.79710502952211,100.00000000000222,59.63137746064476
"accent","orange","#cb4b16",20.54008471816099,94.9010028420928,49.23880751693726
"accent","red","#dc322f",12.553792134784342,82.38578159876946,49.136030452090495
"accent","magenta","#d33682",348.1931179048006,80.96742857455266,49.61859502883098
"accent","violet","#6c71c4",264.29320559619106,57.168958188579964,50.667973029819095
"accent","blue","#268bd2",244.63004140760995,93.43903164239002,55.61332569822655
"accent","cyan","#2aa198",182.32776287881921,91.84316935538897,60.11187225403741
"accent","green","#859900",97.07035644352293,100.0000000000022,59.67940250026341
""",
    # ancillary, not text
    # https://belkadan.com/blog/2024/01/The-Biggest-Smallest-PNG/
    ".png": (
        b"iVBORw0KGgoAAAANSUhEUgAACBAAAAABAQAAAABFwfK3AAAACklEQVR4AWMYBQABAwA"
        b"BRUEDtQAAAABJRU5ErkJggg=="
    ),
    # https://stackoverflow.com/a/24124454
    ".jpg": (
        b"/9j/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE"
        b"BAQEBAQEBAQEBAQEBAQEBAQEBAQH/wgALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAA"
        b"AAAAAAA//aAAgBAQAAAAE//9k="
    ),
    # https://unix.stackexchange.com/a/277967
    ".pdf": (
        b"JVBERi0xLjUKMSAwIG9iajw8L1R5cGUvQ2F0YWxvZy9QYWdlcyAyIDAgUj4+ZW5kb2J"
        b"qCjIgMCBvYmo8PC9UeXBlL1BhZ2VzL0NvdW50IDEvS2lkc1szIDAgUl0+PmVuZG9iag"
        b"ozIDAgb2JqPDwvVHlwZS9QYWdlL01lZGlhQm94WzAgMCA2MTIgNzkyXS9QYXJlbnQgM"
        b"iAwIFIvUmVzb3VyY2VzPDw+Pj4+ZW5kb2JqCjQgMCBvYmo8PC9UeXBlL1hSZWYvU2l6"
        b"ZSA1L1dbMSAxIDFdL1Jvb3QgMSAwIFIvTGVuZ3RoIDE1Pj5zdHJlYW0KAAD/AQkAATQ"
        b"AAWUAAbIAZW5kc3RyZWFtIGVuZG9iagpzdGFydHhyZWYKMTc4CiUlRU9G"
    ),
    # supported primary data files
    # these are at the end because some of them are huge
    # pq.write_table(pa.Table.from_arrays([]), "empty.parquet",
    #                store_schema=False)
    ".parquet": (
        b"UEFSMRUEGRw1ABgGc2NoZW1hFQAAFgAZHBkMFgAWACYAFgAAKCBwYXJxdWV0LWNwcC1"
        b"hcnJvdyB2ZXJzaW9uIDIxLjAuMBkMAEUAAABQQVIx"
    ),
    # asdf.AsdfFile({"v": np.array([0])}).write_to("empty.asdf")
    # not completely empty because a *completely* empty ASDF file has no
    # binary section and no trailing block index
    ".asdf": (
        b"I0FTREYgMS4wLjAKI0FTREZfU1RBTkRBUkQgMS42LjAKJVlBTUwgMS4xCiVUQUcgISB"
        b"0YWc6c3RzY2kuZWR1OmFzZGYvCi0tLSAhY29yZS9hc2RmLTEuMS4wCmFzZGZfbGlicm"
        b"FyeTogIWNvcmUvc29mdHdhcmUtMS4wLjAge2F1dGhvcjogVGhlIEFTREYgRGV2ZWxvc"
        b"GVycywgaG9tZXBhZ2U6ICdodHRwOi8vZ2l0aHViLmNvbS9hc2RmLWZvcm1hdC9hc2Rm"
        b"JywKICBuYW1lOiBhc2RmLCB2ZXJzaW9uOiA1LjEuMH0KaGlzdG9yeToKICBleHRlbnN"
        b"pb25zOgogIC0gIWNvcmUvZXh0ZW5zaW9uX21ldGFkYXRhLTEuMC4wCiAgICBleHRlbn"
        b"Npb25fY2xhc3M6IGFzZGYuZXh0ZW5zaW9uLl9tYW5pZmVzdC5NYW5pZmVzdEV4dGVuc"
        b"2lvbgogICAgZXh0ZW5zaW9uX3VyaTogYXNkZjovL2FzZGYtZm9ybWF0Lm9yZy9jb3Jl"
        b"L2V4dGVuc2lvbnMvY29yZS0xLjYuMAogICAgbWFuaWZlc3Rfc29mdHdhcmU6ICFjb3J"
        b"lL3NvZnR3YXJlLTEuMC4wIHtuYW1lOiBhc2RmX3N0YW5kYXJkLCB2ZXJzaW9uOiAxLj"
        b"QuMH0KICAgIHNvZnR3YXJlOiAhY29yZS9zb2Z0d2FyZS0xLjAuMCB7bmFtZTogYXNkZ"
        b"iwgdmVyc2lvbjogNS4xLjB9CnY6ICFjb3JlL25kYXJyYXktMS4xLjAKICBzb3VyY2U6"
        b"IDAKICBkYXRhdHlwZTogdWludDY0CiAgYnl0ZW9yZGVyOiBsaXR0bGUKICBzaGFwZTo"
        b"gWzFdCi4uLgrTQkxLADAAAAAAAAAAAAAAAAAAAAAIAAAAAAAAAAgAAAAAAAAACH3qNi"
        b"s/rI4AlWpJUqPU9HQAAAAAAAAAACNBU0RGIEJMT0NLIElOREVYCiVZQU1MIDEuMQotL"
        b"S0KLSA2NjIKLi4uCg=="
    ),
    # astropy.io.fits.PrimaryHDU(data=[]).writeto("empty.fits")
    # we regret the length; you are encouraged to find a way to shorten this
    ".fits": (
        b"U0lNUExFICA9ICAgICAgICAgICAgICAgICAgICBUIC8gY29uZm9ybXMgdG8gRklUUyB"
        b"zdGFuZGFyZCAgICAgICAgICAgICAgICAgICAgICBCSVRQSVggID0gICAgICAgICAgIC"
        b"AgICAgICAtNjQgLyBhcnJheSBkYXRhIHR5cGUgICAgICAgICAgICAgICAgICAgICAgI"
        b"CAgICAgICAgIE5BWElTICAgPSAgICAgICAgICAgICAgICAgICAgMSAvIG51bWJlciBv"
        b"ZiBhcnJheSBkaW1lbnNpb25zICAgICAgICAgICAgICAgICAgICAgTkFYSVMxICA9ICA"
        b"gICAgICAgICAgICAgICAgICAwICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC"
        b"AgICAgICAgICAgICAgICAgICBFWFRFTkQgID0gICAgICAgICAgICAgICAgICAgIFQgI"
        b"CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIEVO"
        b"RCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA"
        b"gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC"
        b"AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI"
        b"CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
        b"ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA"
        b"gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC"
        b"AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI"
        b"CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
        b"ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA"
        b"gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC"
        b"AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI"
        b"CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
        b"ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA"
        b"gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC"
        b"AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI"
        b"CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
        b"ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA"
        b"gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC"
        b"AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI"
        b"CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
        b"ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA"
        b"gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC"
        b"AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI"
        b"CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
        b"ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA"
        b"gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC"
        b"AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI"
        b"CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
        b"ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA"
        b"gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC"
        b"AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI"
        b"CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
        b"ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA"
        b"gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC"
        b"AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI"
        b"CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
        b"ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA"
        b"gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC"
        b"AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI"
        b"CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
        b"ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA"
        b"gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC"
        b"AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI"
        b"CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
        b"ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA"
        b"gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC"
        b"AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI"
        b"CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
        b"ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA"
        b"gICAgICAgICAgICAgICAg"
    ),
}

uncompressed_exts = frozenset(UNCOMPRESSED_FILES_DATA.keys())


def to_file_bytes(data: bytes | str) -> bytes:
    if isinstance(data, bytes):
        return b64decode(data)
    else:
        return data.encode("utf-8")


# these are pure functions of static data so they only need to be run once
@pytest.fixture(scope="session")
def compressed_files() -> dict[str, bytes]:
    return {
        ext: to_file_bytes(data) for ext, data in COMPRESSED_FILES_DATA.items()
    }


@pytest.fixture(scope="session")
def uncompressed_files() -> dict[str, bytes]:
    return {
        ext: to_file_bytes(data)
        for ext, data in UNCOMPRESSED_FILES_DATA.items()
    }
