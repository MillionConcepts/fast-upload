# Upload data sets to MAST using the new FAST protocol

This repository contains the `mast-upload` tool for uploading data
sets to [MAST][], the Barbara A. Mikulski Archive for Space Telescopes,
along with assorted support code.

It also contains the software for the data ingestion and validation
server that `mast-upload` interacts with. If you are not administrative 
staff at MAST itself, you will probably not have any use for this.

## Installation

This package will be installable from PyPi in the near future. At present,
install from source: clone the repo to your computer, create a virtual 
environment if you wish, and run `pip install .` from repo root. Python >= 
3.13 is required (>= 3.11 support pending shortly).

## Usage

The primary interface is the `mast-upload` command. Detailed help for it and 
its subcommands are available with `mast-upload --help` and 
`mast-upload <subcommand> --help`.

[basic_usage.md](basic_usage.md) includes step-by-step instructions for a 
standard dataset submission workflow.

[MAST]: https://archive.stsci.edu/
