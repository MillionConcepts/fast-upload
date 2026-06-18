"""
Utility functions for constructing English sentences that talk about
Python objects in a user-friendly manner.
"""

from re import Pattern
from types import GenericAlias, UnionType
from typing import (
    Any,
    get_origin as type_origin,
    get_args as type_args,
)


def a_noun(noun: str) -> str:
    """
    Return 'noun' with the correct English indefinite article prepended
    (e.g. 'a string', 'an integer').

    Implements only the basic a/an rule, not any of the subtleties
    (vocalic Y, "S" pronounced "ess", etc).
    """
    return ("an " if noun[0] in "aeiouAEIOU" else "a ") + noun


def a_type(thing: Any) -> str:
    """
    Return a less cryptic, YAML-flavored version of the name of the
    type of 'thing' (e.g. 'str' becomes 'string' and 'list' becomes
    'sequence') with the correct English indefinite article prepended
    ('a string', 'an integer').

    If 'thing' is already a type object, uses the name of 'thing'
    itself, not the name of type(thing) (which would always be "type").
    """
    if isinstance(thing, UnionType):
        options = [a_type(t) for t in type_args(thing)]
        options.sort(key=lambda s: ("absent value" in s, len(s), s))
        match options:
            case []:
                raise AssertionError(
                    f"{thing!r} is a union type with no alternatives??"
                )
            case [only_option]:
                return only_option
            case [opt_A, opt_B]:
                return f"{opt_A} or {opt_B}"
            case [*most, last]:
                most_poss = ", ".join(most)
                return f"{most_poss}, or {last}"
        # not reached

    if isinstance(thing, GenericAlias):
        args = type_args(thing)
        base = type_origin(thing)
        if base is list:
            assert len(args) == 1
            return f"a sequence of {type_s(args[0])}"
        elif base is dict:
            assert len(args) == 2
            return f"a mapping from {type_s(args[0])} to {type_s(args[1])}"
        else:
            raise NotImplementedError(f"don't know how to describe {thing!r}")

    if isinstance(thing, type):
        name = thing.__name__
    else:
        name = type(thing).__name__

    name = (
        {
            "str": "string",
            "bool": "boolean value",
            "int": "integer",
            "float": "real number",
            "list": "sequence",
            "dict": "mapping",
            "NoneType": "absent value",
            "ExplicitNullT": "null value",
            "ScalarNode": "scalar",
            "SequenceNode": "sequence",
            "MappingNode": "mapping",
        }
    ).get(name, name)

    return a_noun(name)


def type_s(thing: Any) -> str:
    """
    Return a less cryptic, YAML-flavored version of the name of the
    type of 'thing' (e.g. 'str' becomes 'string' and 'list' becomes
    'sequence'), pluralized.

    If 'thing' is already a type object, uses the name of 'thing'
    itself, not the name of type(thing) (which would always be "type").
    """
    if isinstance(thing, UnionType):
        options = [type_s(t) for t in type_args(thing)]
        options.sort(key=lambda s: ("absent value" in s, len(s), s))
        match options:
            case []:
                raise AssertionError(
                    f"{thing!r} is a union type with no alternatives??"
                )
            case [only_option]:
                return only_option
            case [opt_A, opt_B]:
                return f"{opt_A} or {opt_B}"
            case [*most, last]:
                most_poss = ", ".join(most)
                return f"{most_poss}, or {last}"
        # not reached

    if isinstance(thing, GenericAlias):
        args = type_args(thing)
        base = type_origin(thing)
        if base is list:
            assert len(args) == 1
            return f"sequences of {type_s(args[0])}"
        elif base is dict:
            assert len(args) == 2
            return f"mappings from {type_s(args[0])} to {type_s(args[1])}"
        else:
            raise NotImplementedError(f"don't know how to describe {thing!r}")

    if isinstance(thing, type):
        name = thing.__name__
    else:
        name = type(thing).__name__

    pname = (
        {
            "str": "strings",
            "bool": "booleans",
            "int": "integers",
            "float": "real numbers",
            "list": "sequences",
            "dict": "mappings",
            "NoneType": "absent values",
            "ExplicitNullT": "null values",
            "ScalarNode": "scalars",
            "SequenceNode": "sequences",
            "MappingNode": "mappings",
        }
    ).get(name)

    if pname is None:
        pname = f"'{name}'s"

    return pname


def repr_rx(rx: Pattern[Any]) -> str:
    """
    Produce a human-readable, unambiguous serialization of regex RX,
    in the usual /pattern/ notation.
    """
    return "/" + repr(rx.pattern)[1:-1].replace("/", "\\/") + "/"
