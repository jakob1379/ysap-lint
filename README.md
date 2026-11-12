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
| YS101 | use tabs for indentation |
| YS102 | line exceeds 80 columns |
| YS103 | avoid semicolons unless required in control statements |
| YS104 | avoid the `function` keyword |
| YS105 | `then`/`do` on the same line as `if`/`while`/`for` |
| YS106 | no more than one consecutive blank line |
| YS107 | variables created in functions must be `local` |
| YS201 | use `[[ ... ]]` instead of `[ ... ]`/`test` |
| YS202 | use `{1..n}` or C-style loops instead of `seq` |
| YS203 | use `$(...)` instead of backticks |
| YS204 | use `((...))` instead of `let` |
| YS205 | prefer parameter expansion over `basename`/`dirname` |
| YS206 | don't parse the output of `ls` |
| YS301 | useless use of `cat` |
| YS401 | avoid `readonly`; `declare` only for associative arrays |
| YS402 | shebang should be `#!/usr/bin/env bash` |
| YS403 | check `cd` for failure (`cd ... || exit`) |
| YS404 | don't use `set -e` |
| YS405 | never use `eval` |
| YS406 | use lowercase variable names |
| YS501 | quote expansions subject to word splitting |

Not covered (needs dataflow or platform knowledge, not statically lintable):
arrays over space-separated strings, the `read` builtin, GNU-only flag
detection, and `while read` over `for` for line data. All-caps variable names
are assumed to be constants and not flagged; YS301 only checks
head-of-pipeline `cat`; YS206 only catches `ls` inside command substitution.

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
