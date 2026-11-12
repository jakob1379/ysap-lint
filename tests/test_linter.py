from ysap_lint.linter import lint


def codes(source):
    return {d.code for d in lint(source)}


def test_tabs_not_spaces():
    assert "YS101" in codes("if true; then\n    foo\nfi\n")
    assert "YS101" not in codes("if true; then\n\tfoo\nfi\n")


def test_line_length():
    assert "YS102" in codes("echo " + "x" * 90 + "\n")
    assert "YS102" not in codes("echo hi\n")


def test_semicolons():
    assert "YS103" in codes("foo;\n")
    assert "YS103" in codes("foo;\nbar\n")
    assert "YS103" not in codes("if true; then\n\tfoo\nfi\n")
    assert "YS103" not in codes("while true; do\n\tfoo\ndone\n")
    assert "YS103" not in codes("for ((i = 0; i < 5; i++)); do\n\tfoo\ndone\n")
    assert "YS103" not in codes("if true; then foo; fi\n")
    assert "YS103" not in codes("while true; do bar; done\n")
    assert "YS103" not in codes('cd /tmp || { echo failed; exit 1; }\n')


def test_function_keyword():
    assert "YS104" in codes("function foo {\n\ttrue\n}\n")
    assert "YS104" not in codes("foo() {\n\ttrue\n}\n")


def test_then_do_placement():
    assert "YS105" in codes("if true\nthen\n\tfoo\nfi\n")
    assert "YS105" in codes("while true\ndo\n\tfoo\ndone\n")
    assert "YS105" not in codes("if true; then\n\tfoo\nfi\n")
    assert "YS105" not in codes("for f in *; do\n\techo ok\ndone\n")


def test_blank_lines():
    assert "YS106" in codes("foo\n\n\nbar\n")
    assert "YS106" not in codes("foo\n\nbar\n")
    assert "YS106" not in codes("foo\n\n")


def test_local_in_functions():
    assert "YS107" in codes("foo() {\n\tx=5\n}\n")
    assert "YS107" not in codes("foo() {\n\tlocal x=5\n\tx=6\n}\n")
    assert "YS107" not in codes("x=5\n")


def test_single_bracket():
    assert "YS201" in codes('[ -z "$x" ] && foo\n')
    assert "YS201" in codes('test -z "$x" && foo\n')
    assert "YS201" not in codes('[[ -z $x ]] && foo\n')


def test_seq():
    assert "YS202" in codes("for i in $(seq 1 5); do\n\techo ok\ndone\n")
    assert "YS202" not in codes("for i in {1..5}; do\n\techo ok\ndone\n")


def test_backticks():
    assert "YS203" in codes("foo=`date`\n")
    assert "YS203" not in codes("foo=$(date)\n")


def test_let():
    assert "YS204" in codes("let x=1+1\n")
    assert "YS204" not in codes("((x = 1 + 1))\n")


def test_basename_dirname():
    assert "YS205" in codes('name=$(basename "$0")\n')
    assert "YS205" not in codes('name=${0##*/}\n')


def test_parsing_ls():
    assert "YS206" in codes('files=$(ls /tmp)\n')
    assert "YS206" not in codes("for f in *; do\n\techo ok\ndone\n")


def test_useless_cat():
    assert "YS301" in codes("cat file | grep foo\n")
    assert "YS301" not in codes("grep foo < file\n")
    assert "YS301" not in codes("cat file\n")


def test_readonly_declare():
    assert "YS401" in codes("readonly x=5\n")
    assert "YS401" in codes("declare -i x=5\n")
    assert "YS401" not in codes("declare -A map\n")


def test_shebang():
    assert "YS402" in codes("#!/bin/bash\ntrue\n")
    assert "YS402" not in codes("#!/usr/bin/env bash\ntrue\n")
    assert "YS402" not in codes("true\n")
    assert "YS402" not in codes("#!/usr/bin/env python\ntrue\n")
    assert "YS402" not in codes("#!\n")
    assert "YS402" not in codes("#!")


def test_cd_checked():
    assert "YS403" in codes("cd /tmp\n")
    assert "YS403" not in codes("cd /tmp || exit\n")
    assert "YS403" not in codes("cd /tmp && make\n")
    assert "YS403" not in codes("if cd /tmp; then\n\tfoo\nfi\n")


def test_set_e():
    assert "YS404" in codes("set -e\n")
    assert "YS404" in codes("set -euo pipefail\n")
    assert "YS404" in codes("set -o errexit\n")
    assert "YS404" not in codes("set +o errexit\n")
    assert "YS404" not in codes("set -x\n")
    assert "YS404" not in codes('set -- "$@"\n')


def test_eval():
    assert "YS405" in codes('eval "$cmd"\n')


def test_uppercase_vars():
    assert "YS406" in codes("MyVar=1\n")
    assert "YS406" not in codes("my_var=1\n")
    assert "YS406" not in codes("MY_CONST=1\n")
    assert "YS406" not in codes("arr[MY_CONST]=1\n")


def test_subscript_assignment_in_function():
    assert "YS107" not in codes("f() {\n\tdeclare -A m\n\tm[k]=v\n}\n")


def test_unquoted_expansion():
    assert "YS501" in codes("rm $file\n")
    assert "YS501" in codes("rm $(ls /tmp)\n")
    assert "YS501" in codes("for f in $files; do\n\techo ok\ndone\n")
    assert "YS501" not in codes('rm "$file"\n')
    assert "YS501" not in codes('x=$file\n')
    assert "YS501" not in codes('[[ -z $x ]] && foo\n')
    assert "YS501" not in codes('echo "$#"\nret=$?\necho $?\n')


def test_heredoc_content_skipped():
    src = 'cat <<EOF\n    spaces and a very ' + "l" * 100 + ' line\n\n\nEOF\n'
    found = codes(src)
    assert "YS101" not in found
    assert "YS106" not in found


def test_clean_script():
    src = (
        "#!/usr/bin/env bash\n"
        "\n"
        "main() {\n"
        '\tlocal name=${0##*/}\n'
        '\tif [[ -n $name ]]; then\n'
        '\t\techo "$name"\n'
        "\tfi\n"
        "}\n"
        "\n"
        'main "$@"\n'
    )
    assert lint(src) == []


def test_unicode_columns():
    src = 'echo "héllo wörld" $unquoted\n'
    d = next(d for d in lint(src) if d.code == "YS501")
    assert (d.col, d.end_col) == (19, 28)


def test_unreadable_file_exit_code():
    from ysap_lint.cli import main
    assert main(["check", "/nonexistent/missing.sh"]) == 2
