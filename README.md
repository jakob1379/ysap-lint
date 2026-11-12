# ysap-lint

Bash linter and language server for the [ysap style guide](https://style.ysap.sh/).

```sh
nix run . -- check script.sh        # lint files or directories
nix run . -- check --ignore YS102 . # ignore specific rules
nix run . -- server                 # LSP over stdio
```

Output is ruff-style `file:line:col: CODE message`; exit code 1 if any issue is found.

## Rules

| Code  | Rule |
| ----- | ---- |
| YS101 | use tabs for indentation (wrapped lines take 4 extra spaces) |
| YS102 | line exceeds 80 columns (a tab is 8 columns) |
| YS103 | avoid semicolons unless required in control statements |
| YS104 | avoid the `function` keyword |
| YS105 | `then`/`do` on the same line as `if`/`while`/`for` |
| YS106 | no more than one consecutive blank line |
| YS107 | variables created in functions must be `local` |
| YS108 | wrapped pipelines: one command per line, `\` then 4 spaces and a leading `\|` |
| YS201 | use `[[ ... ]]` instead of `[ ... ]`/`test` |
| YS202 | use `{1..n}` or C-style loops instead of `seq` |
| YS203 | use `$(...)` instead of backticks |
| YS204 | use `((...))` instead of `let` |
| YS205 | prefer parameter expansion over `basename`/`dirname` |
| YS206 | don't parse the output of `ls` |
| YS207 | use `((...))` instead of `[[ $a -gt $b ]]` |
| YS301 | useless use of `cat` |
| YS401 | avoid `readonly`; `declare` only for associative arrays |
| YS402 | shebang should be `#!/usr/bin/env bash` |
| YS403 | check `cd`/`pushd` for failure (`cd ... \|\| exit`) |
| YS404 | don't use `set -e` |
| YS405 | never use `eval` |
| YS406 | use lowercase variable names |
| YS501 | quote expansions subject to word splitting |
| YS502 | single quotes for strings without expansions |

Every labelled example in the guide is a test case
(`tests/guide_examples.json`): the "right" ones lint clean, the "wrong" ones
are flagged.

Where the guide leaves room, the linter stays quiet:

- YS107 only flags variables the function itself creates. Assigning a
  variable that also exists at the top level, or an `ALL_CAPS` one (a
  constant, or the shell's own like `PS1`), is taken as intended.
- YS406 flags mixed case only. `FOO=bar` may be a constant, which the guide
  allows, so all-caps names and anything passed to `export` are not flagged.
- YS501 does not flag a variable run as the command (`if $debug; then`),
  the guide's own exception, nor `$?`, `$#`, `$$`, `$RANDOM` and the like.
- YS402: a deliberate `#!/bin/bash` needs `--ignore YS402`.

Not covered (needs dataflow or platform knowledge): arrays over
space-separated strings, the `read` builtin, GNU-only flags, `while read`
over `for` for line data, `sed`/`awk` where parameter expansion would do,
and `true && { ... }` blocks (indistinguishable from the common
`cmd || { ...; exit 1; }`).

tree-sitter-bash cannot parse some valid bash (`exec {fd}<>file`,
`${x//a/\&b}`, `$(((x == 1)) && ...)`). Nothing is reported on the lines it
fails on.

Directories are searched for `*.sh`, `*.bash` and extensionless files with a
bash shebang; hidden directories are skipped.

## Editor setup

Any LSP client works; point it at `ysap-lint server` for bash/sh filetypes.
Neovim example:

```lua
vim.lsp.start({ name = 'ysap-lint', cmd = { 'ysap-lint', 'server' } })
```

## Development

```sh
nix develop -c python -m pytest tests/
```
