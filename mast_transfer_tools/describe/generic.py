"""
Generic (i.e. format-independent) logic for describing individual
files and merging descriptions of individual files into descriptions
of classes of files.
"""

# Note: this file cannot reference the format-specific description
# modules at all, as this would create a circular dependency, which
# Python's import machinery cannot handle.  Anything that needs to
# know about those modules, needs to be either _in_ those modules,
# or in describe/__init__.py.

import dataclasses
import re

from collections import defaultdict
from pathlib import Path
from typing import Any, Collection


GROUPPAT = re.compile(r"(.*?)((?:_|\d)*\d+)$")
"""Suffix patterns we auto-recognize for repeated objects."""


@dataclasses.dataclass
class FileDescription:
    """Simple dataclass for holding file descriptions."""
    fn: Path
    standard: str | None = None
    objects: list[dict[str, Any]] | None = None
    errors: list[str] = dataclasses.field(default_factory=list)
    warnings: list[Warning] = dataclasses.field(default_factory=list)


def sanitize_object_description(obj: dict) -> dict:
    """
    Clean temporary identifiers added by unify_descriptions() functions in
    order to sanitize a description for usage in constructing Filetypes and
    DataObjects.
    """
    for k in ("group_id", "stem"):
        obj.pop(k, "")
    if "schema" in obj:
        obj["schema"] = list(obj["schema"].values())
        for c in obj["schema"]:
            for k in ("group_id", "stem"):
                c.pop(k, "")
    return obj


def unify_obj_description(
    existing: dict, new: dict
) -> tuple[dict, str | None]:
    """
    Attempt to 'unify' two object descriptions.

    Returns:
        unified: dict describing object unified from `existing` and `new`.
        failure: string describing failure if unification failed; None if it
            succeeded
    """
    unified = new.copy()
    failures = []
    unified_name, name_failures = unify_name(existing, new)
    if name_failures is not None:
        failures += name_failures
    else:
        unified |= unified_name
    if existing is not None:
        for k in ("ndim", "stem", "dtype", "objtype", "value", "value_regex"):
            if new.get(k) != existing.get(k):
                failures.append(
                    f"mismatched {k}: {new.get(k)} vs. {existing.get(k)}"
                )
    if existing is not None and ("schema" in existing) != ("schema" in new):
        failures.append("schema presence not consistent")
    # we actually unify schema in a prior pass and insert them into the
    # unified description after this -- all we care about here is ensuring
    # that there actually _are_ schema to have unified, although it's unlikely
    # there aren't -- would imply something like a binary table HDU in which
    # some examples had an empty data section and some didn't
    failures = None if len(failures) == 0 else "; ".join(failures)
    return unified, failures


def unify_name(existing: dict, new: dict) -> tuple[dict, str | None]:
    """
    Attempt to unify two name specifications.

    Returns:
        name: dict giving name specification unified from `existing` and `new`
        failure: string describing failure if unification failed; None if it
            succeeded
    """
    if (stem := new.get("stem")) is not None:
        if existing is not None and existing.get("stem") != stem:
            return {}, "mismatched repeated stem"
        if isinstance(stem, str):
            return {
                "repeated": True,
                "name": rf"{stem}((?:_|\d)*\d+)",
                "name_regex": True
            }, None
        return {
            "repeated": True,
            "name": (*stem[:-1], rf"{stem[-1]}((?:_|\d)*\d+)"),
            "name_regex": True
        }, None
    elif existing is not None and existing["name"] != new["name"]:
        namechars = []
        minlen = min(len(existing["name"]), len(new["name"]))
        maxlen = max(len(existing["name"]), len(new["name"]))
        for i in range(minlen):
            if existing["name"][i] != new["name"][i]:
                namechars.append(".")
            else:
                namechars.append(existing["name"][i])
        for i in range(maxlen - minlen):
            namechars.append(".?")
        return {"name": "".join(namechars), "name_regex": True}, None
    return {"name": new["name"]}, None


def unify_column(existing: dict, new: dict) -> tuple[dict, list | None]:
    """
    Attempt to 'unify' two column descriptions.

    Returns:
        column: dict describing column unified from `existing` and `new`
        failures: list of failures if unification failed; empty list if it
            succeeded
    """
    unified = new.copy()
    failures = []
    unified_name, name_failures = unify_name(existing, new)
    if name_failures is not None:
        failures += name_failures
    else:
        unified |= unified_name
    for k in ("ndim", "dtype"):
        if new.get(k) != existing.get(k):
            failures.append(
                f"mismatched {k}: {new.get(k)} vs. {existing.get(k)}"
            )
    return unified, failures


def unify_schema(existing: dict, new: list[dict]) -> tuple[dict, str | None]:
    """
    Attempt to 'unify' two schemata, looking for repeated and variably-named
    columns, checking dtype and ndim match, etc.

    Returns:
        unified: schema created by unifying `existing` and `new`; or, if
            unification failed, an empty dict
        failure: string describing failure if unification failed; None if it
            succeeded
    """
    if existing is not None:
        if set(existing.keys()) != set(c["group_id"] for c in new):
            return {}, "incompatible group count"
        unified = existing
    else:
        unified = {}
    failures = []
    for col in new:
        if col["group_id"] not in unified:
            unified[col["group_id"]] = col
        else:
            unified[col["group_id"]], col_failures = unify_column(
                unified[col["group_id"]], col
            )
            failures += [f"{col['group_id']}: {f}" for f in col_failures]
    failures = None if len(failures) == 0 else "; ".join(failures)
    return unified, failures


def _n_unique_groups(files: list[list[dict]]) -> int:
    """How many unique group counts are there among `files`?"""
    lengths = set()
    for file in files:
        lengths.add(len(set(r["group_id"] for r in file)))
    return len(lengths)


def chunk_repeated_ordered_objects(
    objlists: list[list[dict]]
) -> tuple[list[list[dict]], str | None]:
    """
    Find groups of 'repeated' ordered objects (HDUs or columns)
    shared among all HDU lists or schema described
    in objlists. Limited to finding 'repetitions' defined by variable
    numeric / underscore patterns suffixed to some stem, consistently
    ordered with respect to other HDUs / columns across objlists.

    Returns:
        objlists_mutated: `objlists`, but with "group_id" and "stem" added
            where relevant; or, if grouping failed, None
        failure: string describing failure if grouping failed; None if it
            succeeded
    """
    if _n_unique_groups(objlists) < 2:
        return objlists, None
    # check to see if anything might require
    # grouping
    shared = set(obj.get("name") for obj in objlists[0])
    unshared = set()
    for objlist in objlists[1:]:
        names = set(obj.get("name") for obj in objlist)
        new_shared = shared.intersection(names)
        unshared = unshared.union(shared.symmetric_difference(names))
        shared = new_shared
    stems = set()
    for u in unshared:
        if m := GROUPPAT.match(u):
            stems.add(m.group(1))
    if not stems:
        return objlists, None
    old_stemgroups = None
    for i, objlist in enumerate(objlists):
        _, stemgroups, failure = assign_ordered_stemgroups(objlist, stems)
        if failure is not None:
            return objlists, f"failed grouping on {i}: {failure}"
        if old_stemgroups is not None and old_stemgroups != stemgroups:
            return objlists, f"failed grouping on {i}: inconsistent position"
        old_stemgroups = stemgroups
        objlists[i] = objlist
    return objlists, None


def unify_object_lists(
    objlists: list[list[dict]]
) -> tuple[dict | None, str | None]:
    """
    Attempt to 'unify' an arbitrary number of object lists, including unifying
    any schemata in those objects.

    Returns:
        objects: dict of unified objects (suitable for use in constructing
            `DataObject`s after passing through
            `sanitize_object_description()`) if unification succeeded; None if
            it failed
        failure: string describing failure if unification failed; None if it
            succeeded
    """
    schemata_by_group = defaultdict(list)
    for objlist in objlists:
        for obj in objlist:
            if "schema" not in obj:
                continue
            for i, col in enumerate(obj["schema"]):
                obj["schema"][i] = col | {"group_id": i}
            schemata_by_group[obj["group_id"]].append(obj["schema"])
    unified_schemata = {}
    # first pass: unify schemata
    for gix, schemata in schemata_by_group.items():
        # yes, this is ugly; we rely on indirectly mutating the schemata
        # inplace
        schemata, failure = chunk_repeated_ordered_objects(schemata)
        if failure is not None:
            return None, failure
        for hix, schema in enumerate(schemata):
            unified_schemata[gix], failure = unify_schema(
                unified_schemata.get(gix), schema
            )
            if failure is not None:
                return None, f"failed on schema {gix} example {hix}: {failure}"
    # second pass: unify everything else
    unified = {}
    for i, objlist in enumerate(objlists):
        for j, obj in enumerate(objlist):
            unified[obj["group_id"]], failure = unify_obj_description(
                unified.get(obj["group_id"]), obj
            )
            if failure is not None:
                return (
                    None,
                    f"failed on file {i} obj {j} / {obj['name']}: {failure}",
                )
    for gix, schema in unified_schemata.items():
        unified[gix]["schema"] = schema
    return unified, None


def assign_ordered_stemgroups(
    objs: list[dict],
    stems: Collection[str]
) -> tuple[list[dict], dict[str, int], str | None]:
    """
    Heuristically group object/column names by stemming likely 'repeated'
    names (suffixed with numbers).
    """
    ix, active_stem = -1, None
    stemgroups = {}
    for obj in objs:
        if m := GROUPPAT.match(obj["name"]):
            matches = [s for s in stems if s == m.group(1)]
        else:
            matches = []
        if len(matches) > 1:
            return objs, stemgroups, "redundant stems"
        elif len(matches) == 1:
            if active_stem is None and matches[0] in stemgroups:
                return objs, stemgroups, "repeated group"
            if matches[0] != active_stem:
                ix += 1
                stemgroups[active_stem] = ix
            active_stem = matches[0]
            obj["stem"] = active_stem
        else:
            active_stem = None
            ix += 1
        obj["group_id"] = ix
    return objs, stemgroups, None
