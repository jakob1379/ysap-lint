"""Lint bash source against https://style.ysap.sh/."""

from dataclasses import dataclass

import tree_sitter_bash
from tree_sitter import Language, Parser

LANGUAGE = Language(tree_sitter_bash.language())
_parser = Parser(LANGUAGE)

MAX_LINE_LENGTH = 80
SHEBANG = "#!/usr/bin/env bash"

# expansions that never word-split
_SAFE_EXPANSIONS = {"$?", "$#", "$$", "$!", "$-"}
_SPLITTING_PARENTS = {"command", "command_name", "for_statement", "array"}


@dataclass
class Diagnostic:
    line: int
    col: int
    end_line: int
    end_col: int
    code: str
    message: str


def lint(source: str) -> list[Diagnostic]:
    diags = []
    tree = _parser.parse(source.encode())
    root = tree.root_node

    skip_lines = set()
    for node in _walk(root):
        if node.type == "heredoc_body":
            skip_lines.update(range(node.start_point[0], node.end_point[0] + 1))
        elif node.type in ("string", "raw_string"):
            skip_lines.update(range(node.start_point[0] + 1, node.end_point[0] + 1))

    diags += _lint_lines(source, skip_lines)

    lines_b = source.encode().split(b"\n")
    for d in _lint_tree(root):
        d.col = _codepoint_col(lines_b, d.line, d.col)
        d.end_col = _codepoint_col(lines_b, d.end_line, d.end_col)
        diags.append(d)
    diags.sort(key=lambda d: (d.line, d.col, d.code))
    return diags


def _codepoint_col(lines_b, line, byte_col):
    if line >= len(lines_b):
        return byte_col
    return len(lines_b[line][:byte_col].decode("utf-8", "surrogateescape"))


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _assignment_name(node):
    name = node.child_by_field_name("name")
    if name is not None and name.type == "subscript":
        name = name.children[0]
    return name


def _diag(node, code, message):
    return Diagnostic(
        node.start_point[0], node.start_point[1],
        node.end_point[0], node.end_point[1],
        code, message,
    )


def _lint_lines(source: str, skip_lines: set) -> list[Diagnostic]:
    diags = []
    lines = source.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    blanks = 0
    for i, line in enumerate(lines):
        if i in skip_lines:
            blanks = 0
            continue
        if line.strip() == "":
            blanks += 1
            if blanks == 2:
                diags.append(Diagnostic(
                    i, 0, i, len(line),
                    "YS106", "no more than one consecutive blank line"))
            continue
        blanks = 0
        indent = line[: len(line) - len(line.lstrip(" \t"))]
        if " " in indent:
            diags.append(Diagnostic(
                i, 0, i, len(indent),
                "YS101", "use tabs for indentation, not spaces"))
        if len(line) > MAX_LINE_LENGTH:
            diags.append(Diagnostic(
                i, MAX_LINE_LENGTH, i, len(line),
                "YS102", f"line exceeds {MAX_LINE_LENGTH} columns"))
    if lines and lines[0].startswith("#!") and lines[0].rstrip() != SHEBANG:
        parts = lines[0][2:].strip().split()
        interp = parts[0].rsplit("/", 1)[-1] if parts else ""
        if interp == "env":
            interp = parts[1] if len(parts) > 1 else ""
        if interp.endswith("sh"):
            diags.append(Diagnostic(
                0, 0, 0, len(lines[0]),
                "YS402", f"shebang should be '{SHEBANG}'"))
    return diags


def _lint_tree(root) -> list[Diagnostic]:
    diags = []
    seen_assignments = set()
    for node in _walk(root):
        t = node.type
        if t == ";" and node.parent and node.parent.type != "c_style_for_statement":
            nxt = node.next_sibling
            if nxt is None or nxt.start_point[0] > node.start_point[0]:
                diags.append(_diag(
                    node, "YS103",
                    "avoid semicolons unless required in control statements"))
        elif t == "function_definition":
            if node.children and node.children[0].type == "function":
                diags.append(_diag(
                    node.children[0], "YS104",
                    "avoid the 'function' keyword; use 'name()' instead"))
            diags += _check_function_locals(node, seen_assignments)
        elif t in ("if_statement", "elif_clause"):
            then = next((c for c in node.children if c.type == "then"), None)
            if then is not None and then.prev_sibling is not None \
                    and then.start_point[0] != then.prev_sibling.end_point[0]:
                diags.append(_diag(
                    then, "YS105", "put 'then' on the same line as 'if'"))
        elif t == "do_group":
            prev = node.prev_sibling
            if prev is not None and node.start_point[0] != prev.end_point[0]:
                diags.append(_diag(
                    node, "YS105",
                    "put 'do' on the same line as 'while'/'for'"))
        elif t == "test_command":
            if node.children and node.children[0].type == "[":
                diags.append(_diag(
                    node, "YS201", "use [[ ... ]] instead of [ ... ]"))
        elif t == "command":
            diags += _check_command(node)
        elif t == "command_substitution":
            if node.children and node.children[0].type == "`":
                diags.append(_diag(
                    node, "YS203", "use $(...) instead of backticks"))
            for sub in _walk(node):
                if sub.type == "command_name" and sub.text == b"ls":
                    diags.append(_diag(
                        node, "YS206", "don't parse the output of ls; "
                        "loop over files directly (for f in *)"))
                    break
            diags += _check_expansion(node)
        elif t == "declaration_command":
            diags += _check_declaration(node)
        elif t in ("expansion", "simple_expansion"):
            diags += _check_expansion(node)
        elif t == "variable_assignment":
            name = _assignment_name(node)
            if name is not None:
                text = name.text.decode()
                if text != text.lower() and text != text.upper():
                    diags.append(_diag(
                        name, "YS406",
                        f"use lowercase variable names: '{text}' "
                        "(uppercase only for constants and exports)"))
    return diags


def _check_command(node) -> list[Diagnostic]:
    name_node = next((c for c in node.children if c.type == "command_name"), None)
    if name_node is None:
        return []
    name = name_node.text.decode()
    if name == "test":
        return [_diag(node, "YS201", "use [[ ... ]] instead of test")]
    if name == "seq":
        return [_diag(node, "YS202",
                      "use {1..n} or a C-style for loop instead of seq")]
    if name == "let":
        return [_diag(node, "YS204", "use ((...)) or $((...)) instead of let")]
    if name in ("basename", "dirname"):
        hint = "${var##*/}" if name == "basename" else "${var%/*}"
        return [_diag(node, "YS205",
                      f"prefer parameter expansion ({hint}) over {name}")]
    if name == "eval":
        return [_diag(node, "YS405", "never use eval")]
    if name == "set":
        prev = ""
        for a in (c for c in node.children if c.type == "word"):
            text = a.text.decode()
            if text == "--":
                break
            if (text.startswith("-") and not text.startswith("--")
                    and "e" in text[1:]) \
                    or (text == "errexit" and prev == "-o"):
                return [_diag(node, "YS404",
                              "don't use set -e; check command results yourself")]
            prev = text
        return []
    if name == "cat":
        parent = node.parent
        cat_args = [c for c in node.children
                    if c.is_named and c.type != "command_name"]
        if parent is not None and parent.type == "pipeline" \
                and parent.children and parent.children[0] == node \
                and cat_args \
                and not any(a.text.startswith(b"-") for a in cat_args):
            return [_diag(node, "YS301",
                          "useless use of cat; use redirection or the tool's "
                          "own file handling")]
        return []
    if name == "cd":
        if not _cd_is_checked(node):
            return [_diag(node, "YS403",
                          "check cd for failure: cd ... || exit")]
    return []


def _cd_is_checked(node):
    cur = node
    while cur.parent is not None:
        parent = cur.parent
        if parent.type == "list":
            nxt = cur.next_sibling
            if nxt is not None and nxt.type in ("||", "&&"):
                return True
        elif parent.type in ("if_statement", "elif_clause", "while_statement"):
            return cur.type != "do_group" and not (
                parent.type in ("if_statement", "elif_clause")
                and _after_then(cur, parent))
        elif parent.type in ("negated_command", "pipeline"):
            pass
        elif parent.type in ("do_group", "compound_statement", "subshell",
                             "function_definition", "program"):
            return False
        cur = parent
    return False


def _after_then(node, if_node):
    for child in if_node.children:
        if child == node:
            return False
        if child.type == "then":
            return True
    return True


def _check_declaration(node) -> list[Diagnostic]:
    kind = node.children[0].type if node.children else ""
    if kind == "readonly":
        return [_diag(node, "YS401", "avoid readonly")]
    if kind in ("declare", "typeset"):
        flags = [c.text.decode() for c in node.children
                 if c.type == "word" and c.text.startswith(b"-")]
        if not any("A" in f for f in flags):
            return [_diag(node, "YS401",
                          "use declare only for associative arrays "
                          "(declare -A); use local in functions")]
    return []


def _check_function_locals(func, seen) -> list[Diagnostic]:
    diags = []
    local_names = set()
    for node in _walk(func):
        if node.type == "declaration_command" \
                and node.children[0].type in ("local", "declare", "typeset"):
            for c in node.children:
                if c.type == "variable_assignment":
                    local_names.add(_assignment_name(c).text)
                elif c.type in ("word", "variable_name") \
                        and not c.text.startswith(b"-"):
                    local_names.add(c.text)
    for node in _walk(func):
        if node.type != "variable_assignment":
            continue
        if node.parent is not None \
                and node.parent.type in ("declaration_command", "command"):
            continue
        name = _assignment_name(node)
        if name is None or name.text in local_names or node.id in seen:
            continue
        seen.add(node.id)
        diags.append(_diag(
            node, "YS107",
            f"variable '{name.text.decode()}' created in a function "
            "should be declared local"))
    return diags


def _check_expansion(node) -> list[Diagnostic]:
    text = node.text.decode()
    if text in _SAFE_EXPANSIONS or text.startswith("${#"):
        return []
    parent = node.parent
    if parent is not None and parent.type == "concatenation":
        parent = parent.parent
    if parent is not None and parent.type in _SPLITTING_PARENTS:
        return [_diag(node, "YS501",
                      f'unquoted expansion {text} is subject to word '
                      f'splitting; use "{text}"')]
    return []
