"""Code-intelligence tools: AST symbols, definitions, references, Spring."""

from __future__ import annotations

import os
import re

from ..tools.definition import tool
from ._engine import (
    extract_imports,
    extract_symbols,
    find_references,
    iter_source_files,
    node_name,
    node_text,
    parse,
)

MAX_SYMBOLS = 200
MAX_HITS = 100

JVM_EXTENSIONS = ("java", "kt", "kts")


def _relative(root: str, file_path: str) -> str:
    try:
        return os.path.relpath(file_path, root)
    except ValueError:
        return file_path


@tool
async def symbols(path: str) -> str:
    """Outline a source file: symbol kinds, names and line ranges.

    Language is detected by extension (py/go/java/kt).
    """
    language, tree, source = parse(path)
    extracted = extract_symbols(language, tree, source)
    if not extracted:
        return "(no symbols found)"
    rendered = "\n".join(symbol.render() for symbol in extracted[:MAX_SYMBOLS])
    if len(extracted) > MAX_SYMBOLS:
        rendered += f"\n...[{len(extracted)} symbols total]"
    return rendered


@tool
async def find_symbol(name: str, root: str = ".", kind: str | None = None) -> str:
    """Find definition sites of a symbol across a file tree.

    Optional kind filter (function, class, method, struct...).
    """
    hits: list[str] = []
    for file_path in iter_source_files(root):
        language, tree, source = parse(file_path)
        for symbol in extract_symbols(language, tree, source):
            if symbol.name == name and (kind is None or symbol.kind == kind):
                hits.append(f"{_relative(root, file_path)}:{symbol.line}  {symbol.kind}")
                if len(hits) >= MAX_HITS:
                    hits.append(f"...[capped at {MAX_HITS} hits]")
                    return "\n".join(hits)
    return "\n".join(hits) or f"(no definitions of {name!r} found)"


@tool
async def references(symbol: str, root: str = ".") -> str:
    """Find occurrences of an identifier across a tree, excluding its definitions.

    Heuristic: parser-based, not semantic.
    """
    hits: list[str] = []
    for file_path in iter_source_files(root):
        language, tree, source = parse(file_path)
        for line in find_references(symbol, language, tree, source):
            hits.append(f"{_relative(root, file_path)}:{line}")
            if len(hits) >= MAX_HITS:
                hits.append(f"...[capped at {MAX_HITS} hits]")
                return "\n".join(hits)
    return "\n".join(hits) or f"(no references to {symbol!r} found)"


@tool
async def imports(path: str) -> str:
    """List the imports and package declaration of a source file (py/go/java/kt)."""
    language, tree, source = parse(path)
    extracted = extract_imports(language, tree, source)
    return "\n".join(extracted) or "(no imports)"


# --- Spring (JVM) -----------------------------------------------------------

_MAPPING_ANNOTATIONS = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
    "RequestMapping": "ANY",
}
_CONTROLLER_STEREOTYPES = ("RestController", "Controller")
_BEAN_STEREOTYPES = ("Component", "Service", "Repository", "Configuration")
_QUOTED = re.compile(r'"([^"]*)"')
_CLASS_TYPES = ("class_declaration", "object_declaration")
_METHOD_TYPES = ("method_declaration", "function_declaration")


def _annotations(node, source) -> list[str]:
    """Annotation texts attached to a declaration (java/kotlin modifiers)."""
    texts: list[str] = []
    for child in node.children:
        if child.type == "modifiers":
            for modifier in child.children:
                if "annotation" in modifier.type:
                    texts.append(" ".join(node_text(modifier, source).split()))
    return texts


def _stereotype(annotation_texts: list[str], needles: tuple[str, ...]) -> str | None:
    joined = " ".join(annotation_texts)
    for needle in needles:
        if f"@{needle}" in joined:
            return needle
    return None


def _iter_jvm(root: str):
    for file_path in iter_source_files(root, JVM_EXTENSIONS):
        language, tree, source = parse(file_path)
        yield _relative(root, file_path), language, tree, source


def _endpoints_in_file(tree, source) -> list[str]:
    found: list[str] = []

    def visit(node, controller: str | None, base_path: str) -> None:
        if node.type in _CLASS_TYPES:
            name = node_name(node, source) or ""
            annotations = _annotations(node, source)
            is_controller = (
                controller is not None
                or _stereotype(annotations, _CONTROLLER_STEREOTYPES) is not None
            )
            new_base = base_path
            if "RequestMapping" in " ".join(annotations):
                match = _QUOTED.search(" ".join(annotations))
                new_base = match.group(1) if match else ""
            for child in node.children:
                visit(
                    child,
                    name if is_controller else controller,
                    new_base if is_controller else base_path,
                )
            return
        if node.type in _METHOD_TYPES and controller is not None:
            for annotation in _annotations(node, source):
                for needle, verb in _MAPPING_ANNOTATIONS.items():
                    if f"@{needle}" in annotation:
                        match = _QUOTED.search(annotation)
                        path = match.group(1) if match else ""
                        full_path = (base_path + path) or "/"
                        method = node_name(node, source) or "?"
                        found.append(f"{verb:<7} {full_path:<28} {controller}.{method}")
                        break
        for child in node.children:
            visit(child, controller, base_path)

    visit(tree.root_node, None, "")
    return found


def _beans_in_file(tree, source) -> list[str]:
    found: list[str] = []

    def visit(node, config_class: str | None) -> None:
        if node.type in _CLASS_TYPES:
            name = node_name(node, source) or ""
            annotations = _annotations(node, source)
            stereotype = _stereotype(annotations, _BEAN_STEREOTYPES)
            if stereotype:
                found.append(f"@{stereotype:<15} {name}")
            is_config = "Configuration" in " ".join(annotations)
            for child in node.children:
                visit(child, name if is_config else config_class)
            return
        if node.type in _METHOD_TYPES and config_class is not None:
            method_annotations = _annotations(node, source)
            if any("@Bean" in annotation for annotation in method_annotations):
                found.append(f"@Bean            {config_class}.{node_name(node, source)}")
        for child in node.children:
            visit(child, config_class)

    visit(tree.root_node, None)
    return found


@tool
async def spring_endpoints(root: str = ".") -> str:
    """Map Spring REST endpoints in a java/kotlin tree: HTTP verb, path and handler method."""
    endpoints: list[str] = []
    for relative, _language, tree, source in _iter_jvm(root):
        found = _endpoints_in_file(tree, source)
        if found:
            endpoints.append(f"# {relative}")
            endpoints.extend(found)
    return "\n".join(endpoints) or "(no Spring endpoints found)"


@tool
async def spring_beans(root: str = ".") -> str:
    """List Spring beans in a java/kotlin tree: stereotype classes and @Bean methods."""
    beans: list[str] = []
    for relative, _language, tree, source in _iter_jvm(root):
        found = _beans_in_file(tree, source)
        if found:
            beans.append(f"# {relative}")
            beans.extend(found)
    return "\n".join(beans) or "(no Spring beans found)"


AST_TOOLS = [symbols, find_symbol, references, imports, spring_endpoints, spring_beans]
