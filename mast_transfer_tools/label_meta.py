"""
This file defines the LabelElement class, which is the base class for
all the classes that form the in-memory representation of a MAST label.

LabelElement performs introspective magic to provide dataclasses-
compatible instance fields, augmented with the capability to store
LabelElement objects in YAML files, load them from YAML files,
and detect and gracefully handle errors in human-written YAML labels.

See the docstrings for LabelElement, LabelElement._validate_label,
and special_field for details on how to write a LabelElement subclass.

The decode_as_* functions toward the end of the file are also
part of this module's public interface.  It is recommended to implement
special field decoding in terms of these functions.
"""

import dataclasses
import typing

from datetime import date
from functools import partial, wraps
from types import GenericAlias, MappingProxyType, NoneType, UnionType
from typing import (
    Any,
    Callable,
    ClassVar,
    Iterator,
    Never,
    Self,
    Sequence,
    TypeAlias,
    TypeVar,
    cast,
    dataclass_transform,
    get_origin as type_origin,
    get_args as type_args,
)

from re import Pattern, compile as re_compile
# re.error was renamed to re.PatternError in 3.13
try:
    from re import PatternError     # type: ignore[attr-defined,unused-ignore]
except ImportError:
    from re import error as PatternError

# class field annotations changed their behavior in 3.14
try:
    from annotationlib import (  # type: ignore[import-not-found]
        Format,
        call_annotate_function,
        get_annotate_from_class_namespace
    )
    def _get_class_annotations(body: dict[str, Any]) -> dict[str, Any]:
        # intentionally using Format.VALUE instead of Format.FORWARDREF
        # so that this behaves as closely as possible to the <=3.13 semantics
        if "__annotations__" in body:
            anns: Any = body["__annotations__"]
        elif annotator := get_annotate_from_class_namespace(body):
            anns = call_annotate_function(annotator, format=Format.VALUE)
        else:
            anns = {}
        assert isinstance(anns, dict)
        return anns
except ImportError:
    def _get_class_annotations(body: dict[str, Any]) -> dict[str, Any]:
        anns = body.get("__annotations__", {})
        assert isinstance(anns, dict)
        return anns

# we need to use a couple of internal dataclasses thingies
from dataclasses import (   # type:ignore[attr-defined]
    _FIELDS as dc_FIELDS,
    _is_classvar as is_classvar
)

from dateutil.parser import (
    parse as parse_date,
    ParserError as DateParseError,
)

from yaml import (
    compose as yaml_compose,
    serialize as yaml_serialize,
    BaseLoader,
    MappingNode, ScalarNode, SequenceNode,
    Node as YAMLAny
)

from mast_transfer_tools.utilz.english import a_type

T = TypeVar("T")
U = TypeVar("U")
LE = TypeVar("LE", bound="LabelElement")
FieldType: TypeAlias = type | GenericAlias | UnionType
FieldNode: TypeAlias = YAMLAny

EXPECTED_SCALAR_TAG   = "tag:yaml.org,2002:str"
EXPECTED_SEQUENCE_TAG = "tag:yaml.org,2002:seq"
EXPECTED_MAPPING_TAG  = "tag:yaml.org,2002:map"

__all__ = (
    "DecodingError",
    "EXPECTED_MAPPING_TAG",
    "EXPECTED_SCALAR_TAG",
    "EXPECTED_SEQUENCE_TAG",
    "ExplicitNull",
    "ExplicitNullT",
    "FieldNode",
    "LabelElement",
    "LabelMeta",
    "YAMLAny",
    "decode_as_bool",
    "decode_as_date",
    "decode_as_dict",
    "decode_as_element",
    "decode_as_explicit_null",
    "decode_as_float",
    "decode_as_int",
    "decode_as_itself",
    "decode_as_list",
    "decode_as_mapping",
    "decode_as_regex",
    "decode_as_scalar",
    "decode_as_sequence",
    "decode_as_str",
    "decode_as_union",
    "special_field",
    "to_yaml_repr",
)



class ExplicitNullT:
    """
    Pythonic 'None' in a field's type always means "this field can be
    omitted", and in a field's _value_, always means "this field _was_
    omitted."  Writing 'foo: null' in YAML never produces
    SomeLabelElement(foo=None).

    However, in a very few places, 'null' is a legitimate value of a
    label field, and distinct from the field having been omitted.
    Those fields have ExplicitNullT as their declared type and, when
    'null' (or 'undefined' or 'none', case insensitive) is the
    explicitly given value of that type, they will have the singleton
    ExplicitNull as their value.
    """

    _instance: ClassVar[Self | None] = None

    def __new__(cls: type[Self]) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __str__(self) -> str:
        return "null"

    def __repr__(self) -> str:
        return "ExplicitNull"

ExplicitNull = ExplicitNullT()


class DecodingError(ValueError):
    """Represents failure to decode a value from the YAML representation."""
    def __init__(self, lpath: str, message: str):
        # We define __init__ solely to enforce that all callers pass
        # exactly two arguments.
        super().__init__(lpath, message)


# dataclasses.dataclass options we use.  Label element classes are
# mutable and incomparable, they don't need to be weakref-able,
# and we want all their constructor parameters to be keyword-only.
# We would _like_ to use slots as a minor performance optimization,
# but that runs foul of a recursive class construction issue, see
# commentary in LabelMeta.__new__.
LABEL_ELEMENT_DATACLASS_OPTIONS = {
    "init": True,
    "kw_only": True,
    "repr": True,
    "slots": False,
    "frozen": False,
    "eq": False,
    "order": False,
    "unsafe_hash": False,
    "match_args": False,
    "weakref_slot": False,
}


@dataclasses.dataclass(**LABEL_ELEMENT_DATACLASS_OPTIONS)
class BaseLabelElement:
    """This class defines a few properties that are shared by all
    concrete LabelElement classes and that need to be visible to
    LabelMeta.  Also see LabelElement itself."""

    # Instance properties present in all LabelElement subclasses
    lpath: str = "/"
    _errors: list[tuple[str, str]] = dataclasses.field(
        default_factory = list
    )


_NON_YAML_FIELDS = frozenset(
    field.name for field in dataclasses.fields(BaseLabelElement)
)


_FIELD_TAG_REQUIRED   = "label_meta.required"
_FIELD_TAG_DECODE_IND = "label_meta.decode_ind"
_FIELD_TAG_DECODE_DEP = "label_meta.decode_dep"


@wraps(dataclasses.field)
def special_field(
    *,
    required: bool = False,
    decode_value: Callable[[FieldNode, str], Any] | None = None,
    decode_with_spec:
        Callable[[FieldNode, str, dict[str, Any]], Any] | None = None,
    **kwargs: Any
) -> Any:
    """This function wraps dataclasses.field and adds some additional
    ways fields can have special properties.  Use it in preference to
    dataclasses.field when defining LabelElements, even if you don't
    need any of its special options.

    Set required=True when a field is required to be present in a YAML
    label.  You must still specify a default value, except as noted in
    the docstring for LabelElement; this value will be used when a
    label, erroneously, leaves the field undefined.  Example:

        class TimeInfo(LabelElement):
            observation_start_date: date | None = None
            delivery_start_date: date | None = special_field(
                required=True, default=None
            )


    Set decode_value=<callback> when you need to override the default
    type-based rules for decoding a field from YAML, but you don't
    need any extra information to decide how to decode the field.
    This callback receives the same arguments as are expected by
    the decode_as_<type> family of functions defined at the
    bottom of this file, and should return the decoded value or
    throw a DecodingError (not a plain ValueError!)

    Set decode_with_spec=<callback> when you need to look at the rest
    of the spec for the LabelElement object to determine how to decode
    the field from YAML.  This callback receives all the same arguments
    as the ordinary decode_value callback, plus one more: the partially
    decoded spec object.  All the fields that use the default decoding
    rules, or plain decode_value callbacks, will be decoded first, so
    when writing decode_with_spec callbackes you can assume, for instance,
    that spec["boolean_field"] has a boolean value, not a string.  Example:

        class ColumnObject(LabelElement):
            repeated: bool = False
            name_regex: bool = False
            name: str | re.Pattern[str] = special_field(
                required = True,
                default = "<name missing>",
                decode_with_spec = lambda val, lpath, spec: (
                    label_meta.decode_as_regex(val, lpath)
                        if spec["repeated"] or spec["name_regex"] else
                    label_meta.decode_as_str(val, lpath)
                )
            )
    """
    if decode_value is not None and decode_with_spec is not None:
        raise AssertionError(
            "bug: decode_value and decode_with_spec callbacks"
            " are mutually exclusive"
        )

    our_metadata = {
        _FIELD_TAG_REQUIRED: required,
        _FIELD_TAG_DECODE_IND: decode_value,
        _FIELD_TAG_DECODE_DEP: decode_with_spec
    }

    if "metadata" not in kwargs or kwargs["metadata"] is None:
        kwargs["metadata"] = our_metadata
    else:
        kwargs["metadata"].update(our_metadata)

    return dataclasses.field(**kwargs)


@dataclass_transform(
    eq_default=False,
    order_default=False,
    kw_only_default=True,
    frozen_default=False,
    field_specifiers=(special_field,),
)
class LabelMeta(type):
    """
    Metaclass to be applied to LabelElement.
    See LabelElement for documentation.
    """
    def __new__(
        cls, cname: str, bases: tuple[type, ...], body: dict[str, Any]
    ) -> "LabelMeta":
        if dc_FIELDS in body:
            # this is a recursive call from dataclass()() to this
            # constructor; this only happens when dataclass(slots=True)
            # is used; I'd *like* to do it that way but it causes a bizarre
            # TypeError to be thrown out of the guts of bltinmodule.c
            # uncomment the next line and change "slots":False to "slots":True
            # in LABEL_ELEMENT_DATACLASS_OPTIONS if you feel like trying to
            # debug this
            #return type.__new__(cls, cname, bases, body)
            raise NotImplementedError("LabelElement.__slots__")

        annotations = _get_class_annotations(body)
        for fname, ty in annotations.items():
            # Ignore class variables.
            if is_classvar(ty, typing):
                continue
            try:
                body[fname] = adjust_field_default(
                    ty,
                    body.get(fname, dataclasses.MISSING),
                )
            except (ValueError, NotImplementedError, AssertionError) as e:
                e.args = (f"{cname}.{fname}",) + e.args
                raise

        # hopefully I get an answer to
        # https://discuss.python.org/t/typing-new-in-dataclass-transform-metaclass/105275
        # that lets me get rid of these type:ignore annotations
        label_element_class = dataclasses.dataclass(
            **LABEL_ELEMENT_DATACLASS_OPTIONS
        )
        klass: "LabelMeta" = label_element_class(   # type:ignore[assignment]
            type.__new__(cls, cname, bases, body)   # type:ignore[arg-type]
        )
        fields = dataclasses.fields(klass)          # type:ignore[arg-type]

        attrs = {}
        ind_attrs = []
        dep_attrs = []
        required_attrs = []
        child_attrs = []
        for field in fields:
            # the instance properties defined by BaseLabelElement are
            # not settable from YAML
            if field.name in _NON_YAML_FIELDS:
                continue

            attrs[field.name] = field

            if field.metadata[_FIELD_TAG_DECODE_DEP] is not None:
                dep_attrs.append(field)
            else:
                assert field.metadata[_FIELD_TAG_DECODE_IND] is not None
                ind_attrs.append(field)
            if field.metadata[_FIELD_TAG_REQUIRED]:
                required_attrs.append(field.name)
            if field_holds_child_attrs(field):
                child_attrs.append(field.name)

        required_attrs.sort()
        child_attrs.sort()

        # These have to be written using setattr() because type checkers
        # cannot tell that every type whose metaclass is LabelMeta is
        # also a subclass of LabelElement.
        setattr(klass, "_attributes", MappingProxyType(attrs))
        setattr(klass, "permitted_keys", frozenset(attrs.keys()))
        setattr(klass, "_ind_attrs", tuple(ind_attrs))
        setattr(klass, "_dep_attrs", tuple(dep_attrs))
        setattr(klass, "_required", tuple(required_attrs))
        setattr(klass, "_child_attrs", tuple(child_attrs))
        return klass


class LabelElement(BaseLabelElement, metaclass=LabelMeta):
    """Common functionality for all label element classes.

    Label element classes are dataclasses with a few additional
    features to facilitate loading from YAML.  It is not necessary to
    annotate LabelElement subclasses with @dataclass; LabelElement's
    metaclass handles this for you.

    Define data fields of each label class as you would for
    an ordinary dataclass.  Use label_meta.special_field()
    instead of dataclasses.field(); special_field can do
    everything dataclasses.field can do, plus a few more things.

    Every field must have a default value, even if that
    field is required to be present in a YAML label; it is needed to
    handle the situation where an *erroneous* label omits the field.
    Mark required fields using special_field(required=True, ...).

    There are a few exceptions to "every field must have a default
    value".  If a field's type is a LabelElement subclass, *don't*
    specify a default value for that type; the default will be an
    instance of that subclass with all fields set to *their* defaults.
    Also, as a convenience, if a field's type is a list or a dict, and
    you leave that field with no default, it will be treated the same
    as specifying `list` or `dict` as the default _factory_ for that
    field.  (In other words, the default will be a _new_ empty list or
    empty dict.)

    Many label element classes will need to override the _validate_label
    method; see that function's docstring for details.
    """

    # All data fields that can be set from the YAML.
    # This field is automatically populated by LabelMeta.
    _attributes: ClassVar[MappingProxyType[str, dataclasses.Field[Any]]]

    # The names of all data fields that can be set from the YAML.
    # This field is automatically populated by LabelMeta.
    permitted_keys: ClassVar[frozenset[str]]

    # All data fields that can be set from the YAML without
    # reference to any other field.
    # This field is automatically populated by LabelMeta.
    _ind_attrs: ClassVar[tuple[dataclasses.Field[Any], ...]]

    # All data fields that can be set from the YAML, but we have to
    # know the values of some of the _ind_attrs to do it.
    # This field is automatically populated by LabelMeta.
    _dep_attrs: ClassVar[tuple[dataclasses.Field[Any], ...]]

    # All data fields that contain other label elements.
    # This field is automatically populated by LabelMeta.
    _child_attrs: ClassVar[tuple[str, ...]]

    # All data fields that must be specified in the YAML serialization
    # of the element.  This field is automatically populated by LabelMeta.
    _required: ClassVar[tuple[str, ...]]

    @classmethod
    def _validate_label(
        cls: type[Self], spec: dict[str, Any], lpath: str
    ) -> list[tuple[str, str]]:
        """
        Override this method if your concrete label-element class
        needs to do additional validation and/or type conversion on
        the YAML representation of its kind of label element, beyond
        the automatic checks and conversions done by decode_label.

        CLS is your class, as usual.  SPEC is a partially decoded
        representation of the keyword arguments that will ultimately
        be passed to your class's constructor.  LPATH is the path
        from the label's root element to the element to be constructed.
        "Partially decoded" means:

        * keys of the YAML label that didn't correspond to a declared
          attribute of your class have been filtered out of 'spec'

        * optional attributes that were left out of the YAML label
          have been filled in with their declared defaults

        * values have been converted to the declared type of each
          field, or replaced by the default value if conversion failed

        Modify 'spec' in place to perform any further conversions or
        value adjustments that are required.  Return a list of validation
        error messages, each of which must be a 2-tuple of strings:
        (path, problem).  An empty list means validation was successful.
        """
        return []

    # The methods below this point are part of the public interface of
    # LabelElement.  They should not need to be overridden in subclasses.

    @property
    def children(self) -> Iterator["LabelElement"]:
        """
        Returns a list of all the immediate LabelElement children of
        this element, flattening lists and dicts.
        """
        for cn in self._child_attrs:
            match getattr(self, cn):
                case None:
                    pass
                case LabelElement() as el:
                    yield el
                case list() as l:
                    yield from l
                case dict() as d:
                    yield from d.values()
                case other:
                    raise TypeError(
                        f"{self.lpath}/{cn} should not be {a_type(other)}"
                    )

    @property
    def errors(self) -> dict[str, list[str]]:
        """
        All validation errors observed for this element and its descendants,
        as a dictionary { path : [problems] }.
        """
        errs = { path: [problem] for path, problem in self._errors }
        for c in self.children:
            for path, problems in c.errors.items():
                probs = errs.setdefault(path, [])
                probs += problems
        return errs

    @property
    def valid(self) -> bool:
        """
        True if neither this element nor any of its descendants have any
        validation errors.
        """
        if self._errors:
            return False
        if any(not c.valid for c in self.children):
            return False
        return True

    @classmethod
    def from_yaml(
        cls: type[Self], raw_spec: FieldNode, lpath: str = "/"
    ) -> Self:
        """
        Construct an instance of CLS from a YAML MappingNode, RAW_SPEC.
        MappingNodes are produced by yaml.compose() from key-value
        mappings in YAML documents.

        This function expects that the only YAML tags in the entire
        tree rooted at RAW_SPEC are tag:yaml.org,2002:{map,seq,str},
        used for all MappingNodes, SequenceNodes, and ScalarNodes,
        respectively.  With PyYAML, this is what you get if you pass
        'Loader=yaml.BaseLoader' to yaml.compose.

        LPATH is the path from the label's root element to the
        element to be constructed.
        """
        spec, errors = decode_label(cls, raw_spec, lpath)
        errors.extend(cls._validate_label(spec, lpath))
        return cls(lpath = lpath, _errors = errors, **spec)

    @classmethod
    def from_blank(cls: type[Self], lpath: str = "/") -> Self:
        """
        Construct an instance of CLS from default values for all its fields.
        The result might have errors.
        """
        return cls.from_yaml(
            MappingNode(tag=EXPECTED_MAPPING_TAG, value=[]),
            lpath
        )

    @classmethod
    def from_text(cls, text: str, lpath: str = "/") -> Self:
        """Parse a YAML-format label from the string TEXT."""
        return cls.from_yaml(
            yaml_compose(text, Loader=BaseLoader)
        )

    def as_yaml(self) -> FieldNode:
        """Produce the YAML representation tree corresponding to self."""
        return to_yaml_repr(self)

    def as_text(self) -> str:
        """Produce a textual YAML serialization of self."""
        return yaml_serialize(
            self.as_yaml(),
            encoding=None,
            allow_unicode=True,
        )


#
# Everything below this point is implementation details.
#


def field_holds_child_attrs(field: dataclasses.Field[Any]) -> bool:
    """True if the field 'field' can hold LabelElement objects,
       either directly or as values in a list or dict."""

    def type_holds_child_attrs(ty: FieldType) -> bool:
        if isinstance(ty, GenericAlias):
            args = type_args(ty)
            ty = type_origin(ty)
            if ty is list:
                return type_holds_child_attrs(args[0])
            elif ty is dict:
                return type_holds_child_attrs(args[1])
            elif ty is Pattern:
                # oddly enough, Pattern is generic; you have to write
                # Pattern[str] or Pattern[bytes] in field decls
                return False
            else:
                raise NotImplementedError(
                    f"don't know what to do with {ty!r}"
                )
        elif isinstance(ty, UnionType):
            return any(type_holds_child_attrs(t) for t in type_args(ty))
        else:
            return issubclass(ty, LabelElement)

    assert isinstance(field.type, FieldType)
    return type_holds_child_attrs(field.type)


def adjust_field_default(
    ty: FieldType,
    default: Any
) -> dataclasses.Field[Any]:
    """
    Given a LabelElement field type TY and its default value DEFAULT
    (which may be a dataclasses.Field instance, and should be
    dataclasses.MISSING if there wasn't any default value),
    return an adjusted default value.

    This implements the features that unlike a regular dataclass,
    you can write "some_field: dict = {}" as shorthand for
    "some_field: dict = dataclasses.field(default_factory = dict)",

    This also verifies that default values are present for all fields,
    except when the field _directly_ holds a LabelElement and nothing
    else, or when the field is a list or dict of something
    (in which cases a suitable default is provided).

    Finally, default values that aren't already dataclass.Field objects
    are wrapped in dataclass.Field objects, and our special metadata
    properties are filled in.
    """
    if not isinstance(ty, (type, GenericAlias, UnionType)):
        raise NotImplementedError(
            f"bug: don't know what to do with {ty!r}"
        )

    if isinstance(default, dataclasses.Field):
        # dataclasses.Field.metadata is a read-only MappingProxyType
        # but we need to alter it.
        d_meta = default.metadata.copy()
        d_value = default.default
        d_factory = default.default_factory
    else:
        d_meta = {}
        d_value = default
        d_factory = dataclasses.MISSING

    if d_factory is dataclasses.MISSING:
        if d_value == []:
            d_value = dataclasses.MISSING
            d_factory = list
        elif d_value == {}:
            d_value = dataclasses.MISSING
            d_factory = dict
        elif d_value is dataclasses.MISSING:
            otype = type_origin(ty)
            if otype is None:
                otype = ty
            if otype is list:
                d_factory = list
            elif otype is dict or isinstance(otype, LabelMeta):
                d_factory = dict
            else:
                raise ValueError("default value missing")
    else:
        assert d_value is dataclasses.MISSING

    d_meta.setdefault(_FIELD_TAG_REQUIRED, False)
    d_dep = d_meta.setdefault(_FIELD_TAG_DECODE_DEP, None)
    d_ind = d_meta.setdefault(_FIELD_TAG_DECODE_IND, None)
    if d_dep is not None:
        assert d_ind is None
    elif d_ind is None:
        d_meta[_FIELD_TAG_DECODE_IND] = make_decoder_for_type(ty)

    # typeshed now insists you call dataclasses.field with only one
    # or the other of `default` and `d_factory`
    if d_factory is dataclasses.MISSING:
        return dataclasses.field(default=d_value, metadata=d_meta)
    else:
        assert d_value is dataclasses.MISSING
        # without this cast we get
        # error: Argument "default_factory" to "field" has incompatible type
        #  "_DefaultFactory[Any] | type[list[_T]] | type[dict[_KT, _VT]]";
        #  expected "Callable[[], Field[Any]]"
        # despite all three alternatives satisfying the requested signature
        d_factory = cast(Callable[[], Any], d_factory)
        return dataclasses.field(default_factory=d_factory, metadata=d_meta)


def decode_label(
    cls: type[LabelElement],
    raw_spec: FieldNode,
    lpath: str,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Perform generic validation and type conversion on YAML label input.

    CLS must be a properly defined subclass of LabelElement.
    The only YAML tags in the entire tree rooted at RAW_SPEC must be
    tag:yaml.org,2002:{map,seq,str}, used for all MappingNodes,
    SequenceNodes, and ScalarNodes, respectively.  With PyYAML, this
    is what you get if you pass 'Loader=yaml.BaseLoader' to
    yaml.compose.

    Returns a pair (SPEC, ERRORS).  SPEC is the result of validating
    and converting each field of RAW_SPEC in isolation, according to
    its type.  ERRORS is a list of validation errors, each of which is
    a 2-tuple of strings (path, problem).  If ERRORS is empty, the
    element is valid as far as this function can tell; the class's
    _validate_label hook may add more errors.
    """
    def field_default(
        lp: str,
        field: str,
        desc: dataclasses.Field[Any]
    ) -> Any:
        if isinstance(desc.type, type) and issubclass(desc.type, LabelElement):
            # special case for fields that directly contain label elements
            return desc.type.from_blank(lpath=f"{lp}/{field}")
        elif desc.default is not dataclasses.MISSING:
            return desc.default
        elif desc.default_factory is not dataclasses.MISSING:
            return desc.default_factory()
        else:
            raise AssertionError(f"{lp}/{field}: BUG: no default")

    errors = []
    try:
        spec_items = decode_as_mapping(raw_spec, lpath)
    except DecodingError as e:
        errors.append(e.args)
        spec_items = []

    # avoid getting paths like "//blah"
    lp = "" if lpath == "/" else lpath

    # A MappingNode's value is a list of pairs (key, value), in the
    # order they appeared in the YAML document.  Filter out invalid,
    # extraneous, and duplicate keys.
    non_scalar_key_error = False
    duplicate_key_errors = set()
    spec: dict[str, Any] = {}
    for key_node, value_node in spec_items:
        if not isinstance(key_node, ScalarNode):
            if not non_scalar_key_error:
                errors.append((
                    lpath, "syntax error; all property names must be strings"
                ))
                non_scalar_key_error = True
            continue

        field = key_node.value
        if key_node.tag != EXPECTED_SCALAR_TAG:
            errors.append((
                f"{lp}/{field}",
                "syntax error; explicit YAML tags may not be used"
            ))
            continue

        if field not in cls._attributes:
            errors.append((
                f"{lp}/{field}",
                f"not a valid property for {a_type(cls)}"
            ))
            continue

        if field in spec:
            if field not in duplicate_key_errors:
                errors.append((
                    f"{lp}/{field}",
                    "property appears twice or more in this element"
                ))
                duplicate_key_errors.add(field)
            continue

        spec[field] = value_node

    # Process the fields that can be decoded in isolation.
    for desc in cls._ind_attrs:
        field = desc.name
        fpath = f"{lp}/{field}"
        if field not in spec:
            spec[field] = field_default(lp, field, desc)
            if desc.metadata[_FIELD_TAG_REQUIRED]:
                errors.append((f"{lp}/{field}", "must always be defined"))
            continue

        try:
            spec[field] = desc.metadata[_FIELD_TAG_DECODE_IND](
                spec[field], fpath
            )
        except DecodingError as e:
            spec[field] = field_default(lp, field, desc)
            errors.append(e.args)

    # Now process the fields that can only be decoded after we
    # know the values of other fields.
    for desc in cls._dep_attrs:
        field = desc.name
        fpath = f"{lp}/{field}"
        if field not in spec:
            spec[field] = field_default(lp, field, desc)
            if desc.metadata[_FIELD_TAG_REQUIRED]:
                errors.append((f"{lp}/{field}", "must always be defined"))
            continue

        try:
            spec[field] = desc.metadata[_FIELD_TAG_DECODE_DEP](
                spec[field], fpath, spec
            )
        except DecodingError as e:
            spec[field] = field_default(lp, field, desc)
            errors.append(e.args)

    return spec, errors


# All the decode_as_* functions conform to this signature:
#
#    def decode_as_T(val: FieldNode, lpath: str[, *, ...]) -> T
#
# where VAL is the raw value for the field, a YAML ScalarNode,
# SequenceNode, or MappingNode; and LPATH is the path from the label
# root to the field being decoded.  LPATH is used only for error
# messages.
#
# A few of the functions have additional keyword-only arguments;
# these are supplied by functools.partial() wrappers. decode_label
# expects to have to provide only the two positional arguments.
#
# They always either return a value of type T, or they raise a DecodingError
# whose 'args' is a 2-tuple suitable for inclusion in LabelElement._errors.
# Any other exception thrown out of one of these functions is a bug.


def decode_as_itself(val: FieldNode, lpath: str) -> YAMLAny:
    """Decode YAML value 'val' as itself.  To put it another way,
    don't decode it at all."""
    return val


def decode_as_scalar(val: FieldNode, lpath: str) -> str:
    """Decode YAML value 'val' as a scalar quantity."""
    if not isinstance(val, ScalarNode):
        raise DecodingError(
            lpath,
            f"wrong type; expected a scalar, not {a_type(val)}"
        )
    if val.tag != EXPECTED_SCALAR_TAG:
        raise DecodingError(
            lpath,
            "syntax error; explicit YAML tags may not be used"
        )

    val = val.value
    if not isinstance(val, str):
        raise AssertionError(f"expected str in ScalarNode, got {a_type(val)}")
    return val


def decode_as_sequence(val: FieldNode, lpath: str) -> list[FieldNode]:
    """Decode YAML value 'val' as a sequence."""
    if not isinstance(val, SequenceNode):
        raise DecodingError(
            lpath,
            f"wrong type; expected a sequence, not {a_type(val)}"
        )
    if val.tag != EXPECTED_SEQUENCE_TAG:
        raise DecodingError(
            lpath,
            "syntax error; explicit YAML tags may not be used"
        )

    val = val.value
    if not isinstance(val, list):
        raise AssertionError(
            f"expected list in SequenceNode, got {a_type(val)}"
        )
    for v in val:
        if not isinstance(v, FieldNode):
            raise AssertionError(
                f"expected list of fields in SequenceNode, got {a_type(val)}"
            )
    return val


def decode_as_mapping(
    val: FieldNode, lpath: str
) -> list[tuple[FieldNode, FieldNode]]:
    """Decode YAML value 'val' as a mapping."""
    if not isinstance(val, MappingNode):
        raise DecodingError(
            lpath,
            f"wrong type; expected a mapping, not {a_type(val)}"
        )
    if val.tag != EXPECTED_MAPPING_TAG:
        raise DecodingError(
            lpath,
            "syntax error; explicit YAML tags may not be used"
        )

    val = val.value
    if not isinstance(val, list):
        raise AssertionError(
            f"expected list in MappingNode, got {a_type(val)}"
        )
    for v in val:
        if not isinstance(v, tuple) \
           or not isinstance(v[0], FieldNode) \
           or not isinstance(v[1], FieldNode):
            raise AssertionError(
                f"expected list of kv pairs in MappingNode, got {a_type(val)}"
            )
    return val



def decode_as_str(val: FieldNode, lpath: str) -> str:
    """Decode YAML value 'val' as a string."""
    return decode_as_scalar(val, lpath)


def decode_as_int(val: FieldNode, lpath: str) -> int:
    """Decode YAML value 'val' as an integer."""
    val = decode_as_scalar(val, lpath)

    try:
        # JSON and YAML recognize only decimal numbers.
        # We're a little bit more generous and accept Python-style
        # integer literals, i.e. the '0x', '0b', and '0o' prefixes
        # indicate hexadecimal, binary, and octal respectively, and
        # underscores can be used as digit groupers for readability.
        # The catch is that leading zeros are _forbidden_ (because
        # they _used_ to mean octal).
        return int(val, base=0)

    except ValueError:
        # Python's stock ValueError message for int() sounds
        # bizarre in context.  Substitute something clearer,
        # and sensitive to specific wrinkles in Python's integer
        # literal syntax that users may not be aware of.
        msg = f"bad value; {val!r} could not be parsed as an integer"
        lval = val.strip()

        if lval.startswith("0"):
            msg += (
                f" (leading zeros are not allowed due to historical"
                f" ambiguity of base; if you _meant_ to write an"
                f" octal number, use '0o{lval[1:]}')"
            )
        elif lval.startswith("_") or lval.endswith("_"):
            msg += " (leading or trailing underscores are not allowed)"
        elif "__" in lval:
            msg += " (consecutive underscores are not allowed)"

        raise DecodingError(lpath, msg) from None


def decode_as_float(val: FieldNode, lpath: str) -> float:
    """Decode YAML value 'val' as a floating point number."""
    val = decode_as_scalar(val, lpath)

    try:
        return float(val)

    except ValueError:
        # as with 'int', substitute a better error message
        raise DecodingError(
            lpath,
            f"bad value; {val!r} could not be parsed as a real number"
        ) from None


# used by decode_as_bool
# I thought about allowing all the YAML 1.1 boolean literals, since we
# theoretically know when something's _supposed_ to be a boolean, but
# there are enough cases where something could be either a boolean or
# something else that it's not a good idea.
TRUE_REPS = re_compile(r"(?is)\A\s*(?:1|true)\s*\Z")
FALSE_REPS = re_compile(r"(?is)\A\s*(?:0|false)\s*\Z")


def decode_as_bool(val: FieldNode, lpath: str) -> bool:
    """Decode YAML value 'val' as a boolean (true or false)."""
    val = decode_as_scalar(val, lpath)

    if TRUE_REPS.fullmatch(val):
        return True
    if FALSE_REPS.fullmatch(val):
        return False

    raise DecodingError(
        lpath,
        f"bad value; {val!r} could not be parsed as a boolean value"
    )


def decode_as_date(val: FieldNode, lpath: str) -> date:
    """Decode YAML value 'val' as a date."""
    val = decode_as_scalar(val, lpath)

    try:
        return parse_date(val.strip()).date()

    except DateParseError as e:
        raise DecodingError(
            lpath,
            f"bad value; {val!r} could not be parsed as a date ({e})"
        ) from None


def decode_as_regex(
    val: FieldNode,
    lpath: str,
    *,
    adjust_pattern: Callable[[str], str] | None = None
) -> Pattern[str]:
    """Decode YAML value 'val' as a regex."""
    pat = decode_as_scalar(val, lpath)

    if adjust_pattern is not None:
        pat = adjust_pattern(pat)

    try:
        return re_compile(pat)

    except PatternError as e:
        raise DecodingError(
            lpath,
            f"bad value; {pat!r} could not be parsed as a regex ({e})"
        ) from None


# used by decode_as_explicit_null
NULL_REPS = re_compile(r"(?is)\A\s*(?:null|undefined|none)\s*\Z")


def decode_as_explicit_null(val: FieldNode, lpath: str) -> ExplicitNullT:
    """Decode YAML value 'val' as an explicit null."""
    val = decode_as_scalar(val, lpath)

    if NULL_REPS.fullmatch(val):
        return ExplicitNull

    raise DecodingError(
        lpath,
        f"bad value; {val!r} could not be parsed as an explicit null value"
    )


def decode_as_list(
    val: FieldNode,
    lpath: str,
    *,
    decode_element: Callable[[FieldNode, str], T],
) -> list[T]:
    """
    Decode YAML value 'val' as a list of elements of type T,
    as defined by the decode_element hook.
    """
    # avoid getting paths like "//blah"
    lp = "" if lpath == "/" else lpath

    items: list[FieldNode]
    if isinstance(val, ScalarNode):
        # Whenever a list of scalars is expected, we accept a bare
        # scalar as shorthand for a one-element list.  This shorthand
        # is not available for lists of lists or lists of mappings
        # because that would easily become ambiguous or at least confusing.
        items = [val]
    else:
        items = decode_as_sequence(val, lpath)

    return [
        decode_element(item, f"{lp}/{i}")
        for i, item in enumerate(items)
    ]


def decode_as_dict(
    val: FieldNode,
    lpath: str,
    *,
    decode_kv_key: Callable[[FieldNode, str], U],
    decode_kv_val: Callable[[FieldNode, str], T],
) -> dict[U, T]:
    """
    Decode YAML value 'val' as a dict whose keys are of type U and
    whose values are of type T, as defined by the decode_kv_key and
    decode_kv_val hooks.  We require that U is scalar.
    """
    items = decode_as_mapping(val, lpath)

    # avoid getting paths like "//blah"
    lp = "" if lpath == "/" else lpath
    cooked_val = {}
    for k, v in items:
        dk = decode_kv_key(k, lpath)
        ipath = f"{lp}/{dk}"
        cooked_val[dk] = decode_kv_val(v, ipath)
    return cooked_val


def decode_as_element(
    val: FieldNode,
    lpath: str,
    *,
    element: type[LE],
) -> LE:
    """
    Decode YAML value 'val' as the concrete LabelElement subclass 'element'.
    """
    if not isinstance(val, MappingNode):
        raise DecodingError(
            lpath,
            f"wrong type; expected {a_type(element)}, not {a_type(val)}"
        )
    return element.from_yaml(val, lpath)


def decode_as_union(
    val: Any,
    lpath: str,
    *,
    scalar_alts: Sequence[Callable[[FieldNode, str], Any]] = (),
    scalar_exp_t: FieldType,
    seq_alts: Sequence[Callable[[FieldNode, str], Any]] = (),
    seq_exp_t: FieldType,
    map_alts: Sequence[Callable[[FieldNode, str], Any]] = (),
    map_exp_t: FieldType
) -> Any:
    if isinstance(val, ScalarNode):
        alts = scalar_alts
        exp_t = scalar_exp_t
        exp_tag = EXPECTED_SCALAR_TAG
    elif isinstance(val, SequenceNode):
        alts = seq_alts
        exp_t = seq_exp_t
        exp_tag = EXPECTED_SEQUENCE_TAG
    elif isinstance(val, MappingNode):
        alts = map_alts
        exp_t = map_exp_t
        exp_tag = EXPECTED_MAPPING_TAG
    else:
        match len(scalar_alts), len(seq_alts), len(map_alts):
            case 0, 0, 0:
                raise AssertionError(
                    "bug: decode_as_union called with no alts"
                )
            case _, 0, 0:
                acceptable = "a scalar value"
            case 0, _, 0:
                acceptable = "a sequence"
            case 0, 0, _:
                acceptable = "a mapping"
            case _, _, 0:
                acceptable = "a scalar value or a sequence"
            case _, 0, _:
                acceptable = "a scalar value or a mapping"
            case 0, _, _:
                acceptable = "a sequence or a mapping"
            case _, _, _:
                acceptable = "a scalar value, a sequence, or a mapping"

        raise DecodingError(
            lpath,
            f"wrong type; expected {acceptable}, not {a_type(val)}"
        )

    if val.tag != exp_tag:
        raise DecodingError(
            lpath,
            "syntax error; explicit YAML tags may not be used"
        )

    if len(alts) == 1:
        return alts[0](val, lpath)

    for alt in alts:
        try:
            return alt(val, lpath)
        except DecodingError:
            pass

    raise TypeError(
        lpath,
        f"bad value; could not parse {val!r} as any of: {a_type(exp_t)}"
    )



def make_decoder_for_union(
    alts: Sequence[FieldType],
    *,
    scalar_only: bool = False,
) -> Callable[[FieldNode, str], Any]:
    """
    Specialize 'decode_as_union' to parse a value as one of the
    alternatives given by ALTS.  If SCALAR_ONLY is True, all of
    the alternatives must be scalar (not sequences or mappings).
    """

    def make_type_union(types: Sequence[FieldType]) -> FieldType:
        if len(types) == 0:
            return list[Never]
        union = types[0]
        for ty in types[1:]:
            union |= ty
        return union

    seq_alts = []
    seq_exp_t = []
    map_alts = []
    map_exp_t = []

    # Alternative parsers for scalar quantities must be tried in a
    # specific order, because the syntax of 'int', 'float', and 'bool'
    # overlaps, and the syntax of 'str' accepts anything.
    # These are the only scalar types we currently need to handle here.
    # FIXME: Writing a quoted string in the YAML should force it to
    # be treated as a string, but that information has been lost by
    # the time we get here.
    scalar_alts: list[None | Callable[[Any, str], Any]] = [
        # int, float, bool, null, str
        None, None, None, None, None
    ]
    scalar_exp_t: list[type | GenericAlias | UnionType] = []

    for alt in alts:
        if alt is None or alt is NoneType:
            # there is no value that parses as None, it's reserved to
            # mean "this field was omitted"
            continue
        if alt is int:
            scalar_alts[0] = decode_as_int
            scalar_exp_t.append(alt)
            continue
        if alt is float:
            scalar_alts[1] = decode_as_float
            scalar_exp_t.append(alt)
            continue
        if alt is ExplicitNullT:
            scalar_alts[2] = decode_as_explicit_null
            scalar_exp_t.append(alt)
            continue
        if alt is bool:
            scalar_alts[3] = decode_as_bool
            scalar_exp_t.append(alt)
            continue
        if alt is str:
            scalar_alts[4] = decode_as_str
            scalar_exp_t.append(alt)
            continue
        if isinstance(alt, GenericAlias):
            base = type_origin(alt)
            if base is list:
                if scalar_only:
                    raise AssertionError(f"bug: {alt!r} is not a scalar type")
                seq_exp_t.append(alt)
                seq_alts.append(make_decoder_for_type(alt))
                continue
            if base is dict:
                if scalar_only:
                    raise AssertionError(f"bug: {alt!r} is not a scalar type")
                map_exp_t.append(alt)
                map_alts.append(make_decoder_for_type(alt))
                continue

        raise NotImplementedError(
            f"don't know what to do with {alt!r}"
        )

    return partial(
        decode_as_union,
        scalar_alts = tuple(d for d in scalar_alts if d is not None),
        scalar_exp_t = make_type_union(scalar_exp_t),
        seq_alts = tuple(seq_alts),
        seq_exp_t = make_type_union(seq_exp_t),
        map_alts = tuple(map_alts),
        map_exp_t = make_type_union(map_exp_t),
    )


def make_decoder_for_type(
    field_type: FieldType,
    *,
    scalar_only: bool = False,
) -> Callable[[FieldNode, str], Any]:
    """
    Return a function that decodes fields with type 'field_type'.
    This will either be one of the decode_as_* functions, or a
    specialization of one of them.

    If 'scalar_only' is True, throws an exception if 'field_type' is
    not a scalar.
    """
    if isinstance(field_type, UnionType):
        match type_args(field_type):
            case ():
                raise AssertionError(
                    "union type with no alternatives??", field_type
                )
            case (t,):
                return make_decoder_for_type(t, scalar_only=scalar_only)
            case (t, n) | (n, t) if n is NoneType:
                # We don't ever _parse_ something as None.  It can
                # only appear as the value when the field is omitted.
                return make_decoder_for_type(t, scalar_only=scalar_only)
            case many_alternatives:
                return make_decoder_for_union(
                    many_alternatives,
                    scalar_only=scalar_only
                )

    base_type = type_origin(field_type)
    if base_type is None:
        base_type = field_type

    if base_type is str:
        return decode_as_str
    if base_type is int:
        return decode_as_int
    if base_type is float:
        return decode_as_float
    if base_type is bool:
        return decode_as_bool
    if base_type is date:
        return decode_as_date
    if base_type is Pattern:
        return decode_as_regex
    if base_type is ExplicitNull:
        return decode_as_explicit_null
    if base_type is YAMLAny:
        return decode_as_itself

    if base_type is list:
        if scalar_only:
            raise AssertionError(f"bug: {field_type!r} is not a scalar type")
        args = type_args(field_type)
        assert len(args) == 1
        return partial(
            decode_as_list,
            decode_element=make_decoder_for_type(args[0])
        )

    if base_type is dict:
        if scalar_only:
            raise AssertionError(f"bug: {field_type!r} is not a scalar type")
        args = type_args(field_type)
        assert len(args) == 2
        return partial(
            decode_as_dict,
            decode_kv_key=make_decoder_for_type(args[0], scalar_only=True),
            decode_kv_val=make_decoder_for_type(args[1], scalar_only=False),
        )

    if isinstance(base_type, type) and issubclass(base_type, LabelElement):
        return partial(decode_as_element, element=base_type)

    raise NotImplementedError(
        f"bug: don't know how to decode {field_type!r}"
    )


def to_yaml_repr(datum: Any) -> FieldNode:
    """
    Convert a LabelElement, or any of the primitive Python data types
    that might be contained in a LabelElement, to a YAML representation
    tree that would be decoded back to the original by LabelElement.from_yaml
    or by the appropriate decode_as_* function.
    """
    if isinstance(datum, LabelElement):
        kvlist = []
        for k in datum._attributes.keys():
            v = getattr(datum, k)
            if v is None:
                continue
            kvlist.append((to_yaml_repr(k), to_yaml_repr(v)))
        return MappingNode(
            tag   = EXPECTED_MAPPING_TAG,
            value = kvlist
        )

    if isinstance(datum, dict):
        kvlist = []
        for k, v in datum.items():
            if v is None:
                raise AssertionError(
                    f"to_yaml_repr: bug: None as dict value (key: {k!r})"
                )
            kvlist.append((to_yaml_repr(k), to_yaml_repr(v)))
        return MappingNode(
            tag   = EXPECTED_MAPPING_TAG,
            value = kvlist
        )

    if isinstance(datum, (list, tuple)):
        vlist = []
        for v in datum:
            if v is None:
                raise AssertionError("to_yaml_repr: bug: None as list element")
            vlist.append(to_yaml_repr(v))
        return SequenceNode(
            tag   = EXPECTED_SEQUENCE_TAG,
            value = vlist
        )

    if isinstance(datum, str):
        return ScalarNode(
            tag   = EXPECTED_SCALAR_TAG,
            value = datum
        )

    if isinstance(datum, bool):
        return to_yaml_repr("true" if datum else "false")
    if isinstance(datum, (int, float)):
        return to_yaml_repr(str(datum))
    if isinstance(datum, Pattern):
        return to_yaml_repr(datum.pattern)
    if isinstance(datum, date):
        return to_yaml_repr(datum.isoformat())

    if isinstance(datum, YAMLAny):
        return datum
    if datum is ExplicitNull:
        return to_yaml_repr("null")
    if datum is None:
        raise AssertionError("to_yaml_repr: bug: None as scalar datum")

    raise NotImplementedError(
        f"don't know how to represent {datum!r} as a YAML document fragment"
    )
