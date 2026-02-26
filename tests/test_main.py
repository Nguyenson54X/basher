from basher import extract_bash_cmd
import os
import pytest
import basher


class TestRunBash:
    """Test cases for the run_bash function."""

    def test_run_bash_simple_echo(self):
        """Test running a simple echo command."""
        cmd = 'echo "Hello World"'
        result = basher.run_bash(cmd)

        assert "return code: 0" in result
        assert "Hello World" in result
        assert "STDOUT:" in result
        assert "STDERR:" in result

    def test_run_bash_multiple_lines(self):
        """Test running multiple commands."""
        cmd = '''echo "Line 1"
echo "Line 2"
echo "Line 3"'''
        result = basher.run_bash(cmd)

        assert "return code: 0" in result
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result

    def test_run_bash_with_error(self):
        """Test running a command that returns non-zero exit code."""
        cmd = "exit 1"
        result = basher.run_bash(cmd)

        assert "return code: 1" in result

    def test_run_bash_with_stderr(self):
        """Test running a command that outputs to stderr."""
        cmd = 'echo "error message" >&2'
        result = basher.run_bash(cmd)

        assert "return code: 0" in result
        assert "error message" in result

    def test_run_bash_output_truncation(self):
        """Test that output keeps tail when truncated (exceeding 10000 characters)."""
        # Generate a command that produces more than 10000 characters
        cmd = 'for i in $(seq 1 1000); do echo "This is a test line number $i with some extra text"; done'
        result = basher.run_bash(cmd)

        assert "return code: 0" in result
        assert "[... output truncated due to length ...]" in result
        # Verify truncation message appears at the beginning of output section
        stdout_section = result.split("STDOUT:")[1].split("=" * 50)[0]
        assert stdout_section.strip().startswith(
            "[... output truncated due to length ...]"
        )
        # Verify later lines (tail) are present
        assert "line number 1000" in result

    def test_run_bash_empty_command(self):
        """Test running an empty command."""
        cmd = ""
        result = basher.run_bash(cmd)

        assert "return code: 0" in result

    def test_run_bash_with_variables(self):
        """Test running a command with environment variables."""
        cmd = 'VAR="test_value"\necho "Variable is: $VAR"'
        result = basher.run_bash(cmd)

        assert "return code: 0" in result
        assert "Variable is: test_value" in result

    def test_run_bash_with_pipe(self):
        """Test running a command with pipe."""
        cmd = 'echo "hello" | tr "a-z" "A-Z"'
        result = basher.run_bash(cmd)

        assert "return code: 0" in result
        assert "HELLO" in result

    def test_run_bash_exit_code_varies(self):
        """Test different exit codes."""
        for exit_code in [0, 1, 5, 42, 255]:
            cmd = f"exit {exit_code}"
            result = basher.run_bash(cmd)
            assert f"return code: {exit_code}" in result


class TestExtractBashCmd:
    """Test cases for the extract_bash_cmd function."""

    def test_extract_single_bash_command(self):
        """Test extracting a single bash command."""
        content = "Some text <bash>echo hello</bash> more text"
        cmd, err = basher.extract_bash_cmd(content)

        assert err is None
        assert cmd == "echo hello"

    def test_extract_no_bash_command(self):
        """Test extracting when no bash command is present."""
        content = "Some text without any bash command"
        cmd, err = basher.extract_bash_cmd(content)

        assert cmd is None
        assert err is not None
        assert "找不到可以执行的bash命令" in err

    def test_extract_multiple_bash_commands(self):
        """Test extracting multiple bash commands."""
        content = "<bash>echo 1</bash> <bash>echo 2</bash>"
        cmd, err = basher.extract_bash_cmd(content)

        assert cmd is None
        assert err is not None
        assert "一次智能执行一个脚本" in err

    def test_extract_bash_cmd_with_newlines(self):
        """Test extracting bash command with newlines."""
        content = "<bash>echo hello\necho world</bash>"
        cmd, err = basher.extract_bash_cmd(content)

        assert err is None
        assert cmd == "echo hello\necho world"

    def test_extract_bash_cmd_with_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        content = "<bash>  \n  echo hello  \n  </bash>"
        cmd, err = basher.extract_bash_cmd(content)

        assert err is None
        assert cmd == "echo hello"


class TestContextManagement:
    """Test cases for context management functions."""

    def setup_method(self):
        """Clear the global context before each test."""
        basher.g_ctx.clear()

    def teardown_method(self):
        """Clear the global context after each test."""
        basher.g_ctx.clear()

    def test_add_user_content(self):
        """Test adding user content to context."""
        basher.add_user_content("Test message")

        assert len(basher.g_ctx) == 1
        assert basher.g_ctx[0]["role"] == "user"
        assert basher.g_ctx[0]["content"] == "Test message"

    def test_add_ai_content(self):
        """Test adding AI content to context."""
        basher.add_ai_content("AI response")

        assert len(basher.g_ctx) == 1
        assert basher.g_ctx[0]["role"] == "assistant"
        assert basher.g_ctx[0]["content"] == "AI response"

    def test_add_sys_content(self):
        """Test adding system content to context."""
        basher.add_sys_content("System prompt")

        assert len(basher.g_ctx) == 1
        assert basher.g_ctx[0]["role"] == "system"
        assert basher.g_ctx[0]["content"] == "System prompt"

    def test_context_order(self):
        """Test that context maintains correct order."""
        basher.add_sys_content("System")
        basher.add_user_content("User")
        basher.add_ai_content("AI")

        assert len(basher.g_ctx) == 3
        assert basher.g_ctx[0]["role"] == "system"
        assert basher.g_ctx[1]["role"] == "user"
        assert basher.g_ctx[2]["role"] == "assistant"


class TestLoadPrompts:
    """Test cases for the load_prompts function."""

    def test_load_prompts_no_path(self, monkeypatch):
        """Test load_prompts when PROMPTS_PATH is not set."""
        monkeypatch.setattr(basher, "PROMPTS_PATH", None)
        basher.g_prompts.clear()
        basher.load_prompts()
        assert len(basher.g_prompts) == 0

    def test_load_prompts_default_path(self, monkeypatch, tmp_path):
        """Test load_prompts uses default path when env var is not set."""
        # Create a mock default prompts directory
        default_prompts_dir = tmp_path / "basher" / "prompts"
        default_prompts_dir.mkdir(parents=True)
        (default_prompts_dir / "core.txt").write_text("Default core prompt")

        # Temporarily override the DEFAULT_PROMPTS_PATH
        original_default = basher.DEFAULT_PROMPTS_PATH
        monkeypatch.setattr(basher, "DEFAULT_PROMPTS_PATH", str(default_prompts_dir))
        monkeypatch.setattr(basher, "PROMPTS_PATH", str(default_prompts_dir))
        basher.g_prompts.clear()
        basher.load_prompts()

        assert "core.txt" in basher.g_prompts
        assert basher.g_prompts["core.txt"] == "Default core prompt"
        monkeypatch.setattr(basher, "DEFAULT_PROMPTS_PATH", original_default)

    def test_load_prompts_nonexistent_path(self, monkeypatch):
        """Test load_prompts when path does not exist."""
        monkeypatch.setattr(basher, "PROMPTS_PATH", "/nonexistent/path")
        basher.g_prompts.clear()
        basher.load_prompts()
        assert len(basher.g_prompts) == 0

    def test_load_prompts_not_directory(self, monkeypatch, tmp_path):
        """Test load_prompts when path is not a directory."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")
        monkeypatch.setattr(basher, "PROMPTS_PATH", str(file_path))
        basher.g_prompts.clear()
        basher.load_prompts()
        assert len(basher.g_prompts) == 0

    def test_load_prompts_success(self, monkeypatch, tmp_path):
        """Test load_prompts successfully loads prompt files."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        # Create some prompt files
        (prompts_dir / "core.txt").write_text("This is core prompt")
        (prompts_dir / "helper.txt").write_text("This is helper prompt")

        monkeypatch.setattr(basher, "PROMPTS_PATH", str(prompts_dir))
        basher.g_prompts.clear()
        basher.load_prompts()

        assert "core.txt" in basher.g_prompts
        assert "helper.txt" in basher.g_prompts
        assert basher.g_prompts["core.txt"] == "This is core prompt"
        assert basher.g_prompts["helper.txt"] == "This is helper prompt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


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
    assert (
        err
        == "找不到可以执行的bash命令，请给出bash命令。如果你发现任务已经完成，请总结你完成的内容。并输出`<finish />`"
    )


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
