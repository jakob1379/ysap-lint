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


def lines_of(source, code):
    return [d.line + 1 for d in lint(source) if d.code == code]


def test_wrapped_lines_take_four_spaces():
    assert "YS101" not in codes("foo \\\n    | bar \\\n    | baz\n")
    assert "YS101" not in codes(
        "f() {\n\tprintf '%s\\n' \\\n\t    \"$a\"\n}\n")
    assert "YS101" not in codes("foo &&\n    bar\n")
    assert "YS101" in codes("foo \\\n  bar\n")
    assert "YS101" in codes("foo\n    bar\n")
    assert "YS101" not in codes("x=$'a\n    b'\n")


def test_line_length_counts_tabs_as_eight_columns():
    assert "YS102" in codes("\t" + "x" * 73 + "\n")
    assert "YS102" not in codes("\t" + "x" * 72 + "\n")
    (d,) = lint("\t" + "x" * 73 + "\n")
    assert (d.col, d.end_col) == (73, 74)


def test_crlf_is_not_content():
    assert "YS102" not in codes("x" * 80 + "\r\n")
    assert lines_of("foo\r\n\r\n\r\nbar\r\n", "YS106") == [3]


def test_semicolons_joining_commands():
    assert "YS103" in codes("foo; # comment\n")
    assert "YS103" in codes("echo hi; echo bye\n")
    assert "YS103" in codes("f() {\n\ta=1; b=2\n}\n")
    assert "YS103" not in codes("case $x in\n\th) usage; return 0;;\nesac\n")
    assert "YS103" not in codes("f() { a; b; }\n")
    assert "YS103" not in codes(
        "for ((i=0;\n\ti<3; i++)); do\n\tfoo\ndone\n")


def test_do_placement_points_at_the_keyword():
    (d,) = [d for d in lint("while true\ndo\n\tfoo\ndone\n")
            if d.code == "YS105"]
    assert (d.line, d.col, d.end_line, d.end_col) == (1, 0, 1, 2)


def test_blank_heredoc_body_skipped():
    assert "YS106" not in codes("cat <<EOF\n\n\n\nEOF\n")


def test_locals_only_for_variables_the_function_creates():
    assert "YS107" not in codes("x=0\nf() {\n\tx=1\n}\n")
    assert "YS107" not in codes("f() {\n\tCODE=1\n\tPS1=x\n}\n")
    assert "YS107" not in codes("f() {\n\tdeclare -A m\n\tm[k]=v\n}\n")
    assert "YS107" in codes("f() {\n\tdeclare -g x\n\ty=1\n}\n")
    assert "YS107" in codes("f() {\n\tfor i in 1 2; do\n\t\t:\n\tdone\n}\n")
    assert "YS107" in codes(
        "f() {\n\tfor ((i = 0; i < 2; i++)); do\n\t\t:\n\tdone\n}\n")
    assert lines_of("f() {\n\tx=1\n\tx=2\n}\n", "YS107") == [2]


def test_locals_follow_dynamic_scope():
    assert "YS107" not in codes(
        "f() {\n\tlocal x\n\tg() {\n\t\tx=1\n\t}\n}\n")
    assert lines_of(
        "f() {\n\tg() {\n\t\tlocal x\n\t}\n\tx=1\n}\n", "YS107") == [5]


def test_wrapped_pipelines():
    assert lines_of("foo |\n\tbar |\n\tbaz\n", "YS108") == [1, 2]
    assert lines_of("foo | bar \\\n    | baz\n", "YS108") == [1]
    assert lines_of("foo \\\n\t| bar\n", "YS108") == [2]
    assert "YS108" not in codes("f() {\n\tfoo \\\n\t    | bar\n}\n")
    assert "YS108" not in codes(
        "foo | while read -r x; do\n\t:\ndone | bar\n")


def test_parsing_ls_in_pipelines_reported_once():
    assert "YS206" in codes("ls | while read -r f; do\n\t:\ndone\n")
    assert lines_of('x=$(foo "$(ls)")\n', "YS206") == [1]
    assert "YS206" not in codes("ls -l\n")


def test_integer_comparison():
    assert "YS207" in codes("[[ $a -gt $b ]] && foo\n")
    assert "YS207" not in codes("((a > b)) && foo\n")
    assert "YS207" not in codes('[ "$#" -eq 0 ] || foo\n')
    assert "YS207" not in codes("[[ -n $a && $a == b ]] && foo\n")


def test_cat_concatenating_is_not_useless():
    assert "YS301" not in codes("cat a b | grep foo\n")
    assert "YS301" not in codes("cat *.log | grep foo\n")
    assert "YS301" not in codes('cat "$@" | grep foo\n')
    assert "YS301" in codes('cat "$file" | grep foo\n')


def test_declare_that_only_prints():
    assert "YS401" not in codes("declare -p x\n")
    assert "YS401" not in codes("declare -f fn\n")
    assert "YS401" in codes("declare -a x\n")


def test_shebang_only_for_bash():
    assert "YS402" not in codes("#!/bin/zsh\n")
    assert "YS402" not in codes("#!/usr/bin/env fish\n")
    assert "YS402" in codes("#!/bin/sh\n")
    assert "YS402" in codes("#!/usr/bin/env -S bash -x\n")


def test_directory_changes_checked():
    assert "YS403" in codes("x=$(cd /tmp; pwd) || exit\n")
    assert "YS403" in codes("pushd /tmp\n")
    assert "YS403" not in codes("pushd /tmp >/dev/null || exit\n")


def test_set_e_option_parsing():
    assert "YS404" not in codes("set a -e\n")
    assert "YS404" in codes("set -uo errexit\n")
    assert "YS404" in codes("set -o pipefail -e\n")
    assert "YS404" not in codes("set +e\n")


def test_exports_may_be_any_case():
    assert "YS406" not in codes("export Foo=1\n")
    assert "YS406" not in codes("Foo=1\nexport Foo\n")
    assert "YS406" in codes("fooBar=1\n")


def test_expansions_that_need_no_quotes():
    assert "YS501" not in codes(
        "debug=false\nif $debug; then\n\t:\nfi\n$debug && echo hi\n")
    assert "YS501" not in codes("echo $RANDOM $UID ${?}\n")
    assert "YS501" not in codes("if (( $(($a % $b)) > 0 )); then\n\t:\nfi\n")
    assert "YS501" not in codes("line=${line//a/$C&$RST}\n")
    assert "YS501" in codes("$cmd $arg\n")
    assert "YS501" in codes("echo ${f}\n")


def test_messages_are_one_line():
    assert all("\n" not in d.message
               for d in lint("rm $(cat <<EOF\nfoo\nEOF\n)\n"))


def test_single_quotes_for_plain_strings():
    assert "YS502" in codes('foo="hello world"\n')
    assert "YS502" not in codes("foo='hello world'\n")
    assert "YS502" not in codes('foo="hello $name"\nbar="$(date)"\n')
    assert "YS502" not in codes('foo="it\'s"\nbar="a\\tb"\nbaz=""\n')
    assert "YS502" not in codes('echo "${x:-"a b"}"\n')
    assert "YS502" not in codes('cat <<EOF\n"quoted"\nEOF\n')


def test_no_diagnostics_from_code_the_parser_gave_up_on():
    src = ("f() {\n\tlocal s=$SECONDS\n"
           '\techo "$(((s == 1)) && echo a || echo b)"\n}\n\ncode=$?\nn=1\n')
    assert "YS107" not in codes(src)


def test_never_raises():
    lint(" && ".join(["a"] * 3000) + "\n")
    lint("echo " + '"$(echo ' * 400 + "x" + ')"' * 400 + "\n")
    lint("echo \udcff\n")
    lint("")
    lint('f() {\n\tlocal\n\tlocal "$x"=1\n\tif [[ $(( "\n')
