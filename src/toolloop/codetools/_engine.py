"""tree-sitter engine: language registry, parser cache, symbol extraction."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

try:
    import tree_sitter
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        'the code toolset requires tree-sitter: pip install "toolloop[code]"'
    ) from exc

from ..tools.fs import SKIP_DIRS

LANGUAGE_MODULES = {
    "py": "tree_sitter_python",
    "go": "tree_sitter_go",
    "java": "tree_sitter_java",
    "kt": "tree_sitter_kotlin",
    "kts": "tree_sitter_kotlin",
}

SUPPORTED = "python (.py), go (.go), java (.java), kotlin (.kt/.kts)"

NAME_NODE_TYPES = frozenset(
    {"identifier", "field_identifier", "type_identifier", "property_identifier"}
)

SYMBOL_KINDS = {
    "py": {"function_definition": "function", "class_definition": "class"},
    "go": {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_spec": "type",  # refined to struct/interface by its type child
    },
    "java": {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "record_declaration": "record",
        "enum_declaration": "enum",
        "method_declaration": "method",
        "constructor_declaration": "constructor",
    },
    "kt": {
        "class_declaration": "class",
        "object_declaration": "object",
        "function_declaration": "function",
    },
}

IMPORT_KINDS = {
    "py": ("import_statement", "import_from_statement"),
    "go": ("import_spec",),
    "java": ("package_declaration", "import_declaration"),
    "kt": ("package_header", "import"),
}


@dataclass
class Symbol:
    kind: str
    name: str
    line: int  # 1-based
    end_line: int
    parent: str | None = None

    def render(self) -> str:
        location = str(self.line) if self.end_line == self.line else f"{self.line}-{self.end_line}"
        prefix = f"{self.parent}." if self.parent else ""
        return f"{self.kind:<10} {prefix}{self.name}  [{location}]"


_parsers: dict[str, tree_sitter.Parser] = {}


def language_for(path: str) -> str | None:
    extension = Path(path).suffix.lstrip(".").lower()
    return extension if extension in LANGUAGE_MODULES else None


def parser_for(language: str) -> tree_sitter.Parser:
    if language not in _parsers:
        try:
            module = __import__(LANGUAGE_MODULES[language])
        except ImportError as exc:
            raise ImportError(
                f'{LANGUAGE_MODULES[language]} is required: pip install "toolloop[code]"'
            ) from exc
        _parsers[language] = tree_sitter.Parser(tree_sitter.Language(module.language()))
    return _parsers[language]


def parse(path: str) -> tuple[str, tree_sitter.Tree, bytes]:
    language = language_for(path)
    if language is None:
        raise ValueError(f"unsupported language for {path!r}; supported: {SUPPORTED}")
    source = Path(path).read_bytes()
    return language, parser_for(language).parse(source), source


def node_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode(errors="replace")


def node_name(node, source: bytes) -> str | None:
    named = node.child_by_field_name("name")
    if named is None:
        for child in node.children:
            if child.is_named and child.type in NAME_NODE_TYPES:
                named = child
                break
    return node_text(named, source) if named is not None else None


def extract_symbols(language: str, tree: tree_sitter.Tree, source: bytes) -> list[Symbol]:
    kinds = SYMBOL_KINDS[language]
    symbols: list[Symbol] = []

    def visit(node, container: str | None) -> None:
        kind = kinds.get(node.type)
        if kind is not None:
            if node.type == "type_spec":  # go: struct? interface?
                type_child = node.child_by_field_name("type")
                child_type = type_child.type if type_child is not None else ""
                kind = {"struct_type": "struct", "interface_type": "interface"}.get(
                    child_type, "type"
                )
            name = node_name(node, source)
            if name:
                symbols.append(
                    Symbol(
                        kind=kind,
                        name=name,
                        line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        parent=container,
                    )
                )
                container = name  # nested symbols report their parent
        for child in node.children:
            visit(child, container)

    visit(tree.root_node, None)
    return symbols


def extract_imports(language: str, tree: tree_sitter.Tree, source: bytes) -> list[str]:
    wanted = IMPORT_KINDS[language]
    imports: list[str] = []

    def visit(node) -> None:
        if node.type in wanted:
            text = " ".join(node_text(node, source).split()).rstrip(";")
            if text:
                imports.append(text)
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return imports


DEFINING_TYPES = frozenset(
    SYMBOL_KINDS["py"] | SYMBOL_KINDS["go"] | SYMBOL_KINDS["java"] | SYMBOL_KINDS["kt"]
) | {
    "type_spec",
}
IDENTIFIER_TYPES = frozenset({"identifier", "type_identifier", "field_identifier"})


def find_references(name: str, language: str, tree: tree_sitter.Tree, source: bytes) -> list[int]:
    """Line numbers where ``name`` occurs as an identifier, excluding its
    definition sites (the name child of a defining node).

    Heuristic by design: tree-sitter is a parser, not a semantic index —
    occurrences include same-named identifiers in unrelated scopes.
    """
    definition_ids: set[int] = set()
    occurrences: list[int] = []

    def visit(node) -> None:
        if node.type in DEFINING_TYPES:
            named = node.child_by_field_name("name")
            if named is not None and node_text(named, source) == name:
                definition_ids.add(named.id)
        for child in node.children:
            visit(child)

    visit(tree.root_node)

    def collect(node) -> None:
        if node.type in IDENTIFIER_TYPES and node.id not in definition_ids:
            if node_text(node, source) == name:
                occurrences.append(node.start_point[0] + 1)
        for child in node.children:
            collect(child)

    collect(tree.root_node)
    return occurrences


def iter_source_files(root: str, extensions: tuple[str, ...] | None = None) -> Iterator[str]:
    """Walk ``root`` skipping VCS/dependency dirs, yielding matching source files."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for filename in sorted(filenames):
            extension = Path(filename).suffix.lstrip(".").lower()
            if extensions is not None and extension not in extensions:
                continue
            if extensions is None and extension not in LANGUAGE_MODULES:
                continue
            yield os.path.join(dirpath, filename)
