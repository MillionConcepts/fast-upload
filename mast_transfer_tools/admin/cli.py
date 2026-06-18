"""Manage uploads to MAST, the Mikulski Archive for Space Telescopes.

This module defines a command-line interface to administration of the
MAST upload server.  Its functions cannot usefully be used as part of
a larger program.  The other modules in this subpackage define a
Pythonic interface that _can_ be used by other programs.
"""

import sys

import click


@click.group(
    epilog="Use 'mast-upload <command> --help' for help on a specific command."
)
@click.version_option(package_name="mast_transfer_tools")
def main() -> None:
    """Manage uploads to MAST, the Mikulski Archive for Space Telescopes."""
    pass


if __name__ == "__main__":
    sys.exit(main())
