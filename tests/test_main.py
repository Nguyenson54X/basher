from basher import extract_bash_cmd

def test_extract_bash_cmd_success():
    """single bash cmd"""
    s = "<bash>ls -la</bash>"
    ret, err = extract_bash_cmd(s)
    assert err is None
    assert ret == "ls -la"


def test_extract_bash_cmd_with_whitespace():
    """bash cmd with blanks"""
    s = "<bash>\n  ls -la  \n</bash>"
    ret, err = extract_bash_cmd(s)
    assert err is None
    assert ret == "ls -la"


def test_extract_bash_cmd_no_bash():
    """no bash command"""
    s = "这是一个普通文本"
    ret, err = extract_bash_cmd(s)
    assert ret is None
    assert err == "找不到可以执行的bash命令，请给出bash命令"


def test_extract_bash_cmd_multiple_bash():
    """multiple bash cmds"""
    s = "<bash>ls -la</bash><bash>pwd</bash>"
    ret, err = extract_bash_cmd(s)
    assert ret is None
    assert err == "一次智能执行一个脚本，请给出单个bash脚本段"


def test_extract_bash_cmd_empty_bash():
    """empty bash cmd"""
    s = "<bash></bash>"
    ret, err = extract_bash_cmd(s)
    assert err is None
    assert ret == ""


def test_extract_bash_cmd_multiline():
    """multiple line bash cmd"""
    s = """<bash>
cd /tmp
ls -la
</bash>"""
    ret, err = extract_bash_cmd(s)
    assert err is None
    assert ret == "cd /tmp\nls -la"
