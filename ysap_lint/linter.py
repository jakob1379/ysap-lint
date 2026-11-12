"""Lint bash source against https://style.ysap.sh/."""

import re
from dataclasses import dataclass

import tree_sitter_bash
from tree_sitter import Language, Parser

LANGUAGE = Language(tree_sitter_bash.language())
_parser = Parser(LANGUAGE)

MAX_LINE_LENGTH = 80
TAB_WIDTH = 8
SHEBANG = "#!/usr/bin/env bash"

# expansions that never contain whitespace
_SAFE_VARIABLES = {
    "?", "#", "$", "!", "-", "RANDOM", "UID", "EUID", "PPID", "LINENO",
    "SECONDS", "BASHPID", "OPTIND", "SHLVL",
}
_SPLITTING_PARENTS = {"command", "command_name", "for_statement", "array"}
_NUMERIC_TESTS = {b"-eq", b"-ne", b"-gt", b"-ge", b"-lt", b"-le"}
_CAT_FILE_ARGS = {
    "word", "string", "raw_string", "simple_expansion", "expansion",
    "concatenation", "number",
}
_CONTINUATION = re.compile(r"(\\|\||&&)$")
_CONTINUATION_INDENT = re.compile(r"\t*    $")


@dataclass
class Diagnostic:
    line: int
    col: int
    end_line: int
    end_col: int
    code: str
    message: str


def lint(source: str) -> list[Diagnostic]:
    data = source.encode("utf-8", "replace")
    root = _parser.parse(data).root_node
    lines = [line.removesuffix("\r") for line in source.split("\n")]

    skip_lines = set()
    error_lines = set()
    for node in _walk(root):
        if node.type == "heredoc_redirect":
            skip_lines.update(
                range(node.start_point[0] + 1, node.end_point[0] + 1))
        elif node.type in ("string", "raw_string", "ansi_c_string"):
            skip_lines.update(
                range(node.start_point[0] + 1, node.end_point[0] + 1))
        # tree-sitter-bash fails on some valid bash; what it reports around
        # a parse error is noise, so it is dropped
        if node.is_error or node.is_missing:
            error_lines.update(
                range(node.start_point[0], node.end_point[0] + 1))

    diags = _lint_lines(lines, skip_lines)

    lines_b = data.split(b"\n")
    for d in _lint_tree(root, lines):
        if d.line in error_lines:
            continue
        d.col = _codepoint_col(lines_b, d.line, d.col)
        d.end_col = _codepoint_col(lines_b, d.end_line, d.end_col)
        diags.append(d)
    diags.sort(key=lambda d: (d.line, d.col, d.code))
    return diags


def _codepoint_col(lines_b, line, byte_col):
    if line >= len(lines_b):
        return byte_col
    return len(lines_b[line][:byte_col].decode("utf-8", "surrogateescape"))


def _walk(node, into_functions=True):
    stack = [node]
    while stack:
        node = stack.pop()
        yield node
        if not into_functions and node.type == "function_definition":
            continue
        # "$((a % b))" inside ((...)) is misparsed as a command substitution
        if node.type == "command_substitution" \
                and node.text.startswith(b"$(("):
            continue
        stack.extend(reversed(node.children))


def _scope(node):
    """Descendants of node that run in its own function scope."""
    for child in node.children:
        yield from _walk(child, into_functions=False)


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


def _indent(line):
    return line[: len(line) - len(line.lstrip(" \t"))]


def _lint_lines(lines: list, skip_lines: set) -> list[Diagnostic]:
    diags = []
    if lines and lines[-1] == "":
        lines = lines[:-1]
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
        indent = _indent(line)
        # a wrapped line is indented 4 spaces past the statement it continues
        wrapped = i > 0 and _CONTINUATION.search(lines[i - 1].rstrip()) \
            and _CONTINUATION_INDENT.match(indent)
        if " " in indent and not wrapped:
            diags.append(Diagnostic(
                i, 0, i, len(indent),
                "YS101", "use tabs for indentation, not spaces"))
        width = 0
        for col, char in enumerate(line):
            width += TAB_WIDTH - width % TAB_WIDTH if char == "\t" else 1
            if width > MAX_LINE_LENGTH:
                diags.append(Diagnostic(
                    i, col, i, len(line),
                    "YS102", f"line exceeds {MAX_LINE_LENGTH} columns"))
                break
    if lines and lines[0].startswith("#!") and lines[0].rstrip() != SHEBANG:
        parts = lines[0][2:].split()
        interp = parts[0].rsplit("/", 1)[-1] if parts else ""
        if interp == "env":
            interp = next((p for p in parts[1:] if not p.startswith("-")), "")
        if interp in ("bash", "sh"):
            diags.append(Diagnostic(
                0, 0, 0, len(lines[0]),
                "YS402", f"shebang should be '{SHEBANG}'"))
    return diags


def _lint_tree(root, lines) -> list[Diagnostic]:
    diags = []
    globals_ = _created_names(root)
    locals_by_function = {}
    exported = set()
    cased = []
    for node in _walk(root):
        t = node.type
        if t == ";":
            diags += _check_semicolon(node)
        elif t == "function_definition":
            if node.children and node.children[0].type == "function":
                diags.append(_diag(
                    node.children[0], "YS104",
                    "avoid the 'function' keyword; use 'name()' instead"))
            diags += _check_function_locals(node, globals_, locals_by_function)
        elif t in ("if_statement", "elif_clause"):
            then = next((c for c in node.children if c.type == "then"), None)
            if then is not None and then.prev_sibling is not None \
                    and then.start_point[0] != then.prev_sibling.end_point[0]:
                diags.append(_diag(
                    then, "YS105", "put 'then' on the same line as 'if'"))
        elif t == "do_group":
            prev = node.prev_sibling
            if prev is not None and node.children \
                    and node.start_point[0] != prev.end_point[0]:
                diags.append(_diag(
                    node.children[0], "YS105",
                    "put 'do' on the same line as 'while'/'for'"))
        elif t == "pipeline":
            diags += _check_pipeline(node, lines)
        elif t == "test_command":
            if node.children and node.children[0].type == "[":
                diags.append(_diag(
                    node, "YS201", "use [[ ... ]] instead of [ ... ]"))
        elif t == "binary_expression":
            op = node.child_by_field_name("operator")
            test = node.parent
            while test is not None and test.type != "test_command":
                test = test.parent
            if op is not None and op.text in _NUMERIC_TESTS \
                    and test is not None and test.children[0].type == "[[":
                diags.append(_diag(
                    node, "YS207", "use ((...)) for integer comparison "
                    f"instead of [[ ... {op.text.decode()} ... ]]"))
        elif t == "command":
            diags += _check_command(node)
        elif t == "command_substitution":
            if node.children and node.children[0].type == "`":
                diags.append(_diag(
                    node, "YS203", "use $(...) instead of backticks"))
            diags += _check_expansion(node)
        elif t == "declaration_command":
            diags += _check_declaration(node)
            if node.children[0].type == "export":
                exported.update(_declared_names(node))
        elif t in ("expansion", "simple_expansion"):
            diags += _check_expansion(node)
        elif t == "string":
            diags += _check_string(node)
        elif t == "variable_assignment":
            name = _assignment_name(node)
            if name is not None:
                text = name.text.decode()
                if text != text.lower() and text != text.upper():
                    cased.append(name)
    for name in cased:
        text = name.text.decode()
        if text not in exported:
            diags.append(_diag(
                name, "YS406",
                f"use lowercase variable names: '{text}' "
                "(uppercase only for constants and exports)"))
    return diags


def _has_ancestor(node, type_):
    while node.parent is not None:
        node = node.parent
        if node.type == type_:
            return True
    return False


def _check_semicolon(node) -> list[Diagnostic]:
    parent = node.parent
    if parent is None \
            or parent.type in ("c_style_for_statement", "case_item"):
        return []
    nxt = node.next_sibling
    trailing = nxt is None or nxt.type == "comment" \
        or nxt.start_point[0] > node.start_point[0]
    # "a; b" on one line of a multi-line block; one-liners like
    # "{ echo failed; exit 1; }" need their semicolons
    joining = not trailing and nxt.is_named and nxt.type != "do_group" \
        and (parent.type == "program"
             or parent.start_point[0] != parent.end_point[0])
    if trailing or joining:
        return [_diag(
            node, "YS103",
            "avoid semicolons unless required in control statements")]
    return []


def _check_pipeline(node, lines) -> list[Diagnostic]:
    diags = []
    pipes = [c for c in node.children if c.type in ("|", "|&")]
    leading = [p for p in pipes
               if lines[p.start_point[0]][:p.start_point[1]].strip() == ""]
    wanted = _indent(lines[node.start_point[0]]) + "    "
    for pipe in pipes:
        row, col = pipe.start_point
        nxt = pipe.next_sibling
        if nxt is not None and nxt.start_point[0] > row:
            diags.append(_diag(
                pipe, "YS108", "wrapped pipeline: end the line with '\\' "
                "and start the next one with '|'"))
        elif leading and pipe not in leading:
            diags.append(_diag(
                pipe, "YS108", "wrapped pipeline: put each command on its "
                "own line"))
        elif pipe in leading and lines[row][:col] != wanted:
            diags.append(_diag(
                pipe, "YS108", "wrapped pipeline: indent continuation "
                "lines 4 spaces"))
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
    if name == "ls":
        parent = node.parent
        piped = parent is not None and parent.type == "pipeline" \
            and parent.children[-1] != node
        if piped or _has_ancestor(node, "command_substitution"):
            return [_diag(node, "YS206", "don't parse the output of ls; "
                          "loop over files directly (for f in *)")]
        return []
    if name == "eval":
        return [_diag(node, "YS405", "never use eval")]
    if name == "set":
        prev = ""
        for arg in node.children[1:]:
            text = arg.text.decode()
            if prev[:1] in ("-", "+") and prev.endswith("o"):
                if prev[0] == "-" and text == "errexit":
                    break
            elif arg.type != "word" or text == "--" \
                    or text[:1] not in ("-", "+"):
                return []
            elif text[0] == "-" and "e" in text:
                break
            prev = text
        else:
            return []
        return [_diag(node, "YS404",
                      "don't use set -e; check command results yourself")]
    if name == "cat":
        parent = node.parent
        args = [c for c in node.children
                if c.is_named and c.type != "command_name"]
        if parent is not None and parent.type == "pipeline" \
                and parent.children[0] == node and len(args) == 1 \
                and args[0].type in _CAT_FILE_ARGS \
                and not args[0].text.startswith(b"-") \
                and not any(c in args[0].text for c in b"*?[@"):
            return [_diag(node, "YS301",
                          "useless use of cat; use redirection or the tool's "
                          "own file handling")]
        return []
    if name in ("cd", "pushd"):
        if not _cd_is_checked(node):
            return [_diag(node, "YS403",
                          f"check {name} for failure: {name} ... || exit")]
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
                             "command_substitution", "function_definition",
                             "program"):
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


def _declaration_flags(node):
    return "".join(c.text.decode() for c in node.children
                   if c.type == "word" and c.text.startswith(b"-"))


def _declared_names(node):
    for c in node.children:
        if c.type == "variable_assignment":
            name = _assignment_name(c)
            if name is not None:
                yield name.text.decode()
        elif c.type in ("word", "variable_name") \
                and not c.text.startswith(b"-"):
            yield c.text.decode()


def _check_declaration(node) -> list[Diagnostic]:
    kind = node.children[0].type if node.children else ""
    if kind == "readonly":
        return [_diag(node, "YS401", "avoid readonly")]
    if kind in ("declare", "typeset"):
        flags = _declaration_flags(node)
        # -p/-f/-F only print, they declare nothing
        if not any(f in flags for f in "ApfF"):
            return [_diag(node, "YS401",
                          "use declare only for associative arrays "
                          "(declare -A); use local in functions")]
    return []


def _created_names(scope, local=False):
    """Names a scope creates: all of them, or only its function-local ones."""
    names = set()
    for node in _scope(scope):
        if node.type == "declaration_command":
            kind = node.children[0].type
            is_local = kind == "local" or (
                kind in ("declare", "typeset")
                and "g" not in _declaration_flags(node))
            if is_local or not local:
                names.update(_declared_names(node))
        elif not local and node.type == "variable_assignment":
            name = _assignment_name(node)
            if name is not None:
                names.add(name.text.decode())
        elif not local and node.type == "for_statement":
            name = node.child_by_field_name("variable")
            if name is not None:
                names.add(name.text.decode())
    return names


def _check_function_locals(func, globals_, locals_by_function):
    # preorder walk: enclosing functions are already in locals_by_function
    locals_by_function[func.id] = _created_names(func, local=True)
    if func.has_error:
        return []
    # bash scoping is dynamic: an enclosing function's locals are visible
    known = set(globals_)
    outer = func
    while outer is not None:
        known |= locals_by_function.get(outer.id, set())
        outer = outer.parent
    diags = []
    for node in _scope(func):
        if node.type == "variable_assignment":
            if node.parent is not None and node.parent.type in (
                    "declaration_command", "command"):
                continue
            name = _assignment_name(node)
        elif node.type == "for_statement":
            name = node.child_by_field_name("variable")
        else:
            continue
        if name is None:
            continue
        text = name.text.decode()
        # ALL_CAPS is a constant or the shell's own (PS1, IFS, COMPREPLY)
        if text in known or text == text.upper():
            continue
        known.add(text)
        diags.append(_diag(
            name, "YS107",
            f"variable '{text}' created in a function "
            "should be declared local"))
    return diags


def _check_string(node) -> list[Diagnostic]:
    if node.children[0].type != '"' \
            or any(c.type != "string_content" for c in node.named_children) \
            or not node.named_children \
            or any(c in node.text for c in b"'\\$`!"):
        return []
    outer = node.parent
    while outer is not None:
        # quotes nested in "${x:-"..."}" or a heredoc are not ours to change
        if outer.type in ("string", "expansion", "heredoc_body"):
            return []
        outer = outer.parent
    return [_diag(node, "YS502",
                  "use single quotes for strings without expansions")]


def _check_expansion(node) -> list[Diagnostic]:
    text = node.text.decode()
    if text.lstrip("${").rstrip("}") in _SAFE_VARIABLES \
            or text.startswith("${#"):
        return []
    parent = node.parent
    if parent is None:
        return []
    # a variable run as the command is controlled by the programmer
    # (if $debug; then ...), which the guide exempts from quoting
    if parent.type == "command_name" and node.type != "command_substitution":
        return []
    if parent.type == "concatenation":
        parent = parent.parent
    if parent is not None and parent.type in _SPLITTING_PARENTS:
        shown = text.split("\n")[0]
        return [_diag(node, "YS501",
                      f'unquoted expansion {shown} is subject to word '
                      f'splitting; use "{shown}"')]
    return []
