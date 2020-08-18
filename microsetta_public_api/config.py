import os
import json
import jsonschema
from abc import abstractmethod


alpha_schema = {
    "type": "string",
    "description":
        "Filepath to an alpha diversity "
        "QZA"
}

alpha_group_schema = {
    "type": "object",
    "additionalProperties": alpha_schema,
    "description": "A group of related alpha diversity objects.",
}

taxonomy_schema = {
    "type": "object",
    "properties": {
        "table": {
            "type": "string",
            "description": "Path to a FeatureTable QZA with features indexed "
                           "on taxonomy",
        },
        "feature-data-taxonomy": {
            "type": "string",
            "description": "Path to a FeatureData[Taxonomy] QZA",
        },
    },
    "required": ["table", "feature-data-taxonomy"],
}


taxonomy_group_schema = {
    "type": "object",
    "additionalProperties": taxonomy_schema,
    "description": "A group of related taxonomies."
}


pcoa_schema = {
    "type": "object",
    "additionalProperties":
        {
            "type": "string",
            "description": "Path to a PCoA QZA",
        },
}


pcoa_group_schema = {
    "type": "object",
    "additionalProperties": pcoa_schema,
    "description": "A group of related PCoAs.",
}


metadata_schema = {
    "type": "string",
    "description": "A filepath to the metadata file.",
}


class Element:

    # need args and kwargs for inheritance concerns
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.data = None

    @abstractmethod
    def accept(self, visitor):
        raise NotImplementedError()

    def gets(self, *args):
        """

        Parameters
        ----------
        *args: Iterable of str or int
            A path of keys

        Returns
        -------
        object
            The object located by the path of keys

        Raises
        ------
        KeyError
            There is no element with the given path of keys

        Examples
        --------
        >>> s = create_literal_element('baz')
        >>> qux = DictElement({'foo': DictElement({'bar': s('baz')})})
        >>> qux.gets('foo', 'bar')
        baz
        >>> qux.gets('foo')
        {'bar': 'baz'}

        """
        if len(args) == 0:
            return self
        first = args[0]
        rest = args[1:]
        try:
            child = self[first]
            # this covers the case when child is str or None or something
            # that is 'gets'able but does not have 'gets' method itself
            if not hasattr(child, 'gets') and len(rest) == 0:
                return child
        # if you can't index into self for whatever reason, give me a key error
        except (TypeError, KeyError, IndexError):
            raise KeyError(first)
        return child.gets(*rest)

    def has(self, *args):
        """

        Parameters
        ----------
        *args: Iterable of str or int
            A path of keys

        Returns
        -------
        bool
           Indicates whether the path of keys exists in the Element


        Examples
        --------
        >>> s = create_literal_element('baz')
        >>> qux = DictElement({'foo': DictElement({'bar': s('baz')})})
        >>> qux.has('foo', 'bar')
        True
        >>> qux.gets('foo')
        True
        >>> qux.gets('foo', 'corge')
        False

        """
        if len(args) == 0:
            return True
        first = args[0]
        rest = args[1:]
        try:
            next_ = self[first]
            return next_.has(*rest)
        # if you can't index into self for whatever reason, it doesn't exist!
        except (TypeError, KeyError, IndexError):
            return False


class DictElement(dict, Element):

    def accept(self, visitor):
        for val in self.values():
            try:
                val.accept(visitor)
            # if val does not have an accept, do not accept on it
            # good for if the entries of the dict are bool or None, or have
            # not been converted to an Element
            except AttributeError:
                pass

    def updates(self, value, *args):
        """

        Parameters
        ----------
        value: Any
            A value to store at the given path of arguments
        *args: Iterable of str or int
            A path of keys. Must have at least one key.

        Returns
        -------
        None

        """
        if len(args) == 0:
            return ValueError('Must receive at least one key.')

        first = args[0]
        rest = args[1:]

        if len(rest) == 0:
            self.update(DictElement({first: value}))
        elif first in self and isinstance(self[first], dict):
            self[first].updates(value, *rest)
        else:
            self[first] = DictElement()
            self[first].updates(value, *rest)
        return


class ListElement(list, Element):
    def accept(self, visitor):
        for val in self:
            try:
                val.accept(visitor)
            # if val does not have an accept, do not accept on it
            # good for if the entries of the list are bool or None, or have
            # not been converted to an Element
            except AttributeError:
                pass


class AlphaElement(DictElement):
    def accept(self, visitor):
        super().accept(visitor)
        visitor.visit_alpha(self)


class TaxonomyElement(DictElement):
    def accept(self, visitor):
        super().accept(visitor)
        visitor.visit_taxonomy(self)


class PCOAElement(DictElement):
    def accept(self, visitor):
        super().accept(visitor)
        visitor.visit_pcoa(self)


class MetadataElement(str, Element):
    def accept(self, visitor):
        visitor.visit_metadata(self)


class ConfigElementVisitor:

    @abstractmethod
    def visit_alpha(self, element):
        raise NotImplementedError()

    @abstractmethod
    def visit_taxonomy(self, element):
        raise NotImplementedError()

    @abstractmethod
    def visit_pcoa(self, element):
        raise NotImplementedError()

    @abstractmethod
    def visit_metadata(self, element):
        raise NotImplementedError()


class SchemaBase:
    def __init__(self):
        self.alpha_kw = '__alpha__'
        self.taxonomy_kw = '__taxonomy__'
        self.pcoa_kw = '__pcoa__'
        self.metadata_kw = '__metadata__'

    def element_map(self):
        map_ = {
            self.alpha_kw: AlphaElement,
            self.taxonomy_kw: TaxonomyElement,
            self.pcoa_kw: PCOAElement,
            self.metadata_kw: MetadataElement,
        }
        return map_

    @abstractmethod
    def schema(self):
        raise NotImplementedError()

    def validate(self, instance):
        return jsonschema.validate(instance=instance, schema=self.schema())

    def make_elements(self, json_dump):
        if isinstance(json_dump, list):
            for i, entry in enumerate(json_dump):
                json_dump[i] = self.make_elements(entry)
        elif isinstance(json_dump, dict):
            for key, value in json_dump.items():
                json_dump[key] = self.make_elements(value)
                element_type = self.element_map().get(key, None)
                if element_type is not None:
                    json_dump[key] = element_type(json_dump[key])

        return ElementFactory.get_element(json_dump)


class Schema(SchemaBase):
    def schema(self):
        return {
            "type": "object",
            "properties": {
                "datasets":
                    {
                        "type": "object",
                        "properties": {
                            self.metadata_kw: metadata_schema,
                        },
                        "additionalProperties":
                            {
                                "type": "object",
                                "properties": {
                                    self.alpha_kw: alpha_group_schema,
                                    self.taxonomy_kw: taxonomy_group_schema,
                                    self.pcoa_kw: pcoa_group_schema,
                                },
                                "additionalProperties": False,
                            }
                    },
            },
        }


class LegacySchema(SchemaBase):
    def __init__(self):
        self.alpha_kw = 'alpha_resources'
        self.taxonomy_kw = 'table_resources'
        self.pcoa_kw = 'pcoa'
        self.metadata_kw = 'metadata'

    def schema(self):
        return {
            "type": "object",
            "properties": {
                self.alpha_kw: alpha_group_schema,
                self.taxonomy_kw: taxonomy_group_schema,
                self.pcoa_kw: pcoa_group_schema,
                self.metadata_kw: metadata_schema,
            }
        }


class CompatibilitySchema(SchemaBase):
    def __init__(self):
        self.old_alpha_kw = 'alpha_resources'
        self.old_taxonomy_kw = 'table_resources'
        self.old_pcoa_kw = 'pcoa'
        self.old_metadata_kw = 'metadata'
        self.alpha_kw = '__alpha__'
        self.taxonomy_kw = '__taxonomy__'
        self.pcoa_kw = '__pcoa__'
        self.metadata_kw = '__metadata__'

    def element_map(self):
        return {
            self.old_alpha_kw: AlphaElement,
            self.old_taxonomy_kw: TaxonomyElement,
            self.old_pcoa_kw: PCOAElement,
            self.old_metadata_kw: MetadataElement,
            self.alpha_kw: AlphaElement,
            self.taxonomy_kw: TaxonomyElement,
            self.pcoa_kw: PCOAElement,
            self.metadata_kw: MetadataElement,
        }

    def schema(self):
        return {
            "type": "object",
            "properties": {
                self.old_alpha_kw: alpha_group_schema,
                self.old_taxonomy_kw: taxonomy_group_schema,
                self.old_pcoa_kw: pcoa_group_schema,
                self.old_metadata_kw: metadata_schema,
                "datasets":
                    {
                        "type": "object",
                        "properties": {
                            self.metadata_kw: metadata_schema,
                        },
                        "additionalProperties":
                            {
                                "type": "object",
                                "properties": {
                                    self.alpha_kw: alpha_group_schema,
                                    self.taxonomy_kw:
                                        taxonomy_group_schema,
                                    self.pcoa_kw: pcoa_group_schema,
                                },
                                "additionalProperties": False,
                            }
                    },
            }
        }


def create_literal_element(literal):
    class LiteralElement(Element, literal):
        def accept(self, visitor):
            pass
    return LiteralElement


class ElementFactory:

    @staticmethod
    def get_element(obj):
        if obj is None:
            return None
        if isinstance(obj, bool):
            return obj
        if isinstance(obj, int):
            return create_literal_element(int)(obj)
        if isinstance(obj, float):
            return create_literal_element(float)(obj)
        if isinstance(obj, str):
            return create_literal_element(str)(obj)
        if isinstance(obj, list):
            return ListElement(obj)
        if isinstance(obj, dict):
            return DictElement(obj)

        raise NotImplementedError(f"No Element for type: {type(obj)}")


# NOTE: importlib replaces setuptools' pkg_resources as of Python 3.7
# See: https://stackoverflow.com/questions/6028000/how-to-read-a-static-file-from-inside-a-python-package # noqa

PACKAGE_NAME = __name__.split('.')[0]
CONFIG_FILE = os.getenv("MPUBAPI_CFG", "server_config.json")

# ultimately change this to Schema once everything is converted
schema = CompatibilitySchema()

try:
    import importlib.resources as pkg_resources
    with pkg_resources.open_text(PACKAGE_NAME, CONFIG_FILE) as fp:
        SERVER_CONFIG = json.load(fp)
    schema.validate(SERVER_CONFIG['resources'])

except ImportError:
    import pkg_resources
    content = pkg_resources.resource_string(PACKAGE_NAME, CONFIG_FILE)
    SERVER_CONFIG = json.loads(content)
    schema.validate(SERVER_CONFIG['resources'])


resources = dict()
