from ysap_lint.cli import main

CLEAN = "#!/usr/bin/env bash\n\necho 'hi'\n"
DIRTY = "#!/usr/bin/env bash\n\ncd /tmp\n"


def run(capsys, *args):
    code = main(list(args))
    return code, capsys.readouterr().out


def test_clean_file_exits_zero(tmp_path, capsys):
    f = tmp_path / "ok.sh"
    f.write_text(CLEAN)
    assert run(capsys, "check", str(f)) == (0, "")


def test_violation_is_reported_ruff_style(tmp_path, capsys):
    f = tmp_path / "bad.sh"
    f.write_text(DIRTY)
    code, out = run(capsys, "check", str(f))
    assert code == 1
    assert out.splitlines()[0].startswith(f"{f}:3:1: YS403 ")
    assert out.splitlines()[-1] == "Found 1 issue."


def test_ignore_suppresses_rule(tmp_path, capsys):
    f = tmp_path / "bad.sh"
    f.write_text(DIRTY)
    assert run(capsys, "check", "--ignore", "ys403", str(f)) == (0, "")


def test_unreadable_file_exits_two(capsys):
    assert run(capsys, "check", "/nonexistent/missing.sh")[0] == 2


def test_non_utf8_file_exits_two(tmp_path, capsys):
    f = tmp_path / "bin.sh"
    f.write_bytes(b"echo \xff\n")
    assert run(capsys, "check", str(f))[0] == 2


def test_directory_finds_bash_by_extension_and_shebang(tmp_path, capsys):
    (tmp_path / "a.sh").write_text(DIRTY)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "tool").write_text(DIRTY)
    (tmp_path / "script.py").write_text("#!/usr/bin/env python\ncd /tmp\n")
    (tmp_path / "notes").write_text("cd /tmp\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hook").write_text(DIRTY)
    code, out = run(capsys, "check", str(tmp_path))
    assert code == 1
    flagged = sorted(line.split(":")[0] for line in out.splitlines()[:-1])
    assert flagged == [str(tmp_path / "a.sh"), str(tmp_path / "sub" / "tool")]
