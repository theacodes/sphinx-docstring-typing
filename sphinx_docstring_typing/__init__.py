# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import ast
import re
import typing

import sphinx.util.logging


_LOGGER = sphinx.util.logging.getLogger(__name__)

# All available type hints from the typing module.
_TYPES = set(typing.__all__) - set((
    'cast', 'get_type_hints', 'NewType', 'no_type_check',
    'no_type_check_decorator', 'overload', 'TYPE_CHECKING'))

# A pattern that matches any available type hint.
_TYPE_PATTERN = '|'.join(_TYPES)

# Regex used to find & replace type hints.
TYPE_RE = re.compile(r'\*?(({})\[.+\])\*?'.format(_TYPE_PATTERN))

# Bare type hints don't have any arguments, e.g., Any vs List[int].
_BARE_TYPES = ('Any', 'Text', 'Hashable', 'Sized', 'ByteString', 'AnyStr')

# A pattern that matches any bare types.
_BARE_TYPES_PATTERN = '|'.join(_BARE_TYPES)

# Regex used to find & replace bare type hints.
BARE_TYPE_RE = re.compile(
    r'\*?({})(?! ?\[)(?! ?`)\*?'.format(_BARE_TYPES_PATTERN))


class CollapseAttrsVisitor(ast.NodeTransformer):
    """Collapses chained Attribute nodes into a single Name node.

    This makes it easier to wrap the name with a rst reference.

    For example::

        Attribute(
            value=Attribute(
                value=Attribute(
                    value=Name(id='google'),
                    attr='auth'),
                attr='credentials'),
            attr='Credentials')

    Becomes::

        Name(id='google.auth.credentials.Credentials')

    """
    def visit_Attribute(self, node):
        child = self.visit(node.value)
        parent_attr = (
            child.attr if isinstance(child, ast.Attribute) else child.id)
        return ast.Name(id=parent_attr + '.' + node.attr)


class RedocVisitor(ast.NodeVisitor):
    def __init__(self):
        self.output = ''

    def visit_Subscript(self, node):
        self.visit(node.value)
        self.visit(node.slice)

    def visit_Slice(self, node):
        self.generic_visit(node)

    def visit_Tuple(self, node):
        for idx, elt in enumerate(node.elts):
            if idx:
                self.output += ', '
            self.visit(elt)

    def visit_Index(self, node):
        self.output += ' [ '
        self.generic_visit(node)
        self.output += ' ] '

    def visit_Name(self, node):
        name = node.id
        ref = 'py:obj'

        if hasattr(typing, name):
            name = '~typing.' + name

        self.output += ':{ref}:`{name}`'.format(
            ref=ref, name=name)

    def visit_Attribute(self, node):
        self.visit(node.value)
        self.output += '.' + node.attr

    def visit_UnaryOp(self, node):
        if isinstance(node.op, ast.Invert):
            node.operand.id = '~' + node.operand.id
        return self.generic_visit(node)

    def visit_Ellipsis(self, node):
        self.output += '...'


def transform(annotation):
    """Transforms a pep 484 type annotation into rst refences."""
    tree = ast.parse(annotation)
    transformer = CollapseAttrsVisitor()
    tree = transformer.visit(tree)
    visitor = RedocVisitor()
    visitor.visit(tree)
    return visitor.output


def autodoc_process_docstring(
        app, what, name, obj, options, lines):
    """Replaces PEP 484 style type annotations in docstrings with sphinx-style
    references."""

    old_lines = lines[:]

    for n, line in enumerate(lines):
        new_line = line

        try:
            # Check for type hints that take arguments.
            new_line = re.sub(
                TYPE_RE,
                lambda match: transform(match.group(1)),
                new_line)

            # Check for any lingering bare type hints.
            new_line = re.sub(
                BARE_TYPE_RE,
                lambda match: transform(match.group(1)),
                new_line)

        except Exception as e:
            _LOGGER.warn(
                'sphinx-docstring-typing: Un-parseable line in docstring: \n'
                '\t> %s \n\nException: %s' % (line, e))

        if line != new_line:
            _LOGGER.verbose(
                'sphinx-docstring-typing: docstring line for %s replaced: '
                '\n\t> %s \n\t> %s' % (name, line, new_line))
            lines[n] = new_line


def setup(app):
    """Sphinx plug-in entrypont."""
    app.connect('autodoc-process-docstring', autodoc_process_docstring)
