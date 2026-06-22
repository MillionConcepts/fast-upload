# Upload data sets to MAST using the new FAST protocol

This repository contains the `mast-upload` tool for uploading data
sets to [MAST][], the Barbara A. Mikulski Archive for Space Telescopes,
along with assorted support code.

It also contains the software for the data ingestion and validation
server that `mast-upload` interacts with. If you are not administrative 
staff at MAST itself, you will probably not have any use for this.

## Installation

The package is available on PyPi: `pip install mast-transfer-tools`.

Alternatively, install from source: clone the repo to your computer and run 
`pip install .` from repo root. 

Python >= 3.11 is required.

## Usage

The primary interface is the `mast-upload` command. Detailed help for it and 
its subcommands are available with `mast-upload --help` and 
`mast-upload <subcommand> --help`.

[basic_usage.md](/docs/basic_usage.md) includes step-by-step instructions for a 
standard dataset submission workflow.

## Documentation

Additional documentation, including an API reference, is available at 
https://fast-upload.readthedocs.io/en/latest/.

## Tests

You can execute the self-tests by running `pytest` from repo root 
(note that the tests additionally depend on `pytest` and `hypothesis`).

[MAST]: https://archive.stsci.edu/
