#!/usr/bin/env python3
import os
import re
import subprocess
import sys
import tempfile
import threading
from openai import OpenAI

ENDPOINT = os.environ.get("BASHER_API_ENDPOINT", "https://openrouter.ai/api/v1/")
APIKEY = os.environ.get("BASHER_API_KEY")
MODEL = os.environ.get("BASHER_MODEL", "moonshotai/kimi-k2.5")

g_prompts = dict()
g_ctx = list()
g_lock = threading.Lock()


def run_llm(prompt):
    client = OpenAI(base_url=ENDPOINT, api_key=APIKEY)
    response = client.chat.completions.create(model=MODEL, messages=prompt, stream=True)
    full_content = ""
    for chunk in response:
        if chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            print(content, end="", flush=True)
            full_content += content

    print(flush=True)
    return full_content


def add_user_content(content):
    g_ctx.append({"role": "user", "content": content})


def add_ai_content(content):
    g_ctx.append({"role": "assistant", "content": content})


def add_sys_content(content):
    g_ctx.append({"role": "system", "content": content})


def extract_bash_cmd(s):
    pattern = r"<bash>(.*?)</bash>"
    matches = re.findall(pattern, s, re.DOTALL)
    if len(matches) == 0:
        return (
            None,
            "No executable bash commands found. Please provide a bash command. "
            "If you find the task has already been completed, please summarize "
            "what you have done and output <finish />.",
        )
    elif len(matches) > 1:
        return (
            None,
            "Only one script can be executed at a time. Please provide a single"
            "bash script block.",
        )
    else:
        return matches[0].strip(), None


def run_bash(cmd):
    MAX_OUTPUT_LENGTH = 10000

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write("#!/bin/bash\n")
        f.write("set -euo pipefail\n")
        f.write(cmd)
        temp_script_path = f.name
    process = subprocess.Popen(
        ["bash", temp_script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout_parts = []
    stderr_parts = []

    def read_stream(stream, parts_list):
        for line in stream:
            with g_lock:
                parts_list.append(line)
                print(line, flush=True, end="")
        stream.close()

    stdout_thread = threading.Thread(
        target=read_stream, args=(process.stdout, stdout_parts)
    )
    stderr_thread = threading.Thread(
        target=read_stream, args=(process.stderr, stderr_parts)
    )

    stdout_thread.start()
    stderr_thread.start()

    return_code = process.wait()

    stdout_thread.join()
    stderr_thread.join()

    try:
        os.unlink(temp_script_path)
    except OSError:
        pass

    with g_lock:
        stdout_content = "".join(stdout_parts)
        stderr_content = "".join(stderr_parts)
    if len(stdout_content) > MAX_OUTPUT_LENGTH:
        stdout_display = (
            "[... output truncated due to length ...]\n"
            + stdout_content[-MAX_OUTPUT_LENGTH:]
        )
    else:
        stdout_display = stdout_content
    if len(stderr_content) > MAX_OUTPUT_LENGTH:
        stderr_display = (
            "[... output truncated due to length ...]\n"
            + stderr_content[-MAX_OUTPUT_LENGTH:]
        )
    else:
        stderr_display = stderr_content

    result = f"Bash execution completed with return code: {return_code}\n"
    result += "=" * 50 + "\n"
    result += "STDOUT:\n"
    result += stdout_display if stdout_display else "(no output)\n"
    result += "\n" + "=" * 25 + " END OF STDOUT " + "=" * 25 + "\n"
    result += "STDERR:\n"
    result += stderr_display if stderr_display else "(no output)\n"
    result += "\n" + "=" * 25 + " END OF STDERR " + "=" * 25 + "\n"
    print(flush=True)
    return result


def main():
    add_sys_content(sys_prompt())

    agents_md_path = os.path.join(os.getcwd(), "AGENTS.md")
    if os.path.isfile(agents_md_path):
        with open(agents_md_path, "r", encoding="utf-8") as f:
            agents_content = f.read()
        add_user_content("\nHere is the context infomation about this project:\n\n" + agents_content)

    if len(sys.argv) < 2:
        print("Error: Please provide a task description.", flush=True)
        print("Usage: " + sys.argv[0] + " <task_description>", flush=True)
        sys.exit(1)

    add_user_content(" ".join(sys.argv[1:]))
    while True:
        res = run_llm(g_ctx)
        print(flush=True)
        if "<finish />" in res:
            exit(0)
        cmd, err = extract_bash_cmd(res)
        add_ai_content(res)
        if err is not None:
            add_user_content("Format error: " + err)
        else:
            res = run_bash(cmd)
            if res is not None:
                add_user_content(res + "\n\nWhat do we need to do next?")


def sys_prompt():
    return """
You are an AI Agent capable of running bash commands within this environment to
complete the tasks assigned to you by the user.

The only tool you can call is bash. The bash scripts are wrapped in a `<bash>`
`</bash>` block. In each response, you must include at most one `<bash>` block.

### General Workflow

For every task, you MUST follow this workflow:

1. **Understand**: Carefully read and restate the task to confirm understanding.
2. **Explore**: Investigate the codebase structure, locate relevant files.
3. **Plan**: Formulate a step-by-step plan before making any changes.
4. **Implement**: Execute changes incrementally, one logical step at a time.
5. **Check**: Run build/test commands, and try to fix errors.
6. **Summarize**: When done, summarize all changes made.

### Thinking Requirements

Before EVERY `<bash>` command, you MUST:
1. State what you are trying to achieve in this step.
2. Explain why this command is the right approach.
3. Predict what you expect to see in the output.

This helps maintain a clear chain of reasoning and prevents aimless exploration.

### Error Handling

- If a command fails (non-zero return code), **read the STDERR carefully**
  before retrying.
- Do NOT blindly retry the same command. Analyze the error, adjust your
  approach, then try again.
- If you are stuck after 3 attempts on the same step, step back and
  reconsider your overall approach.

### Constraints & Safety Rules

- **Never** run destructive commands like `rm -rf /`, `mkfs`, or anything
  that could damage the system.
- **Never** install packages globally unless explicitly asked.
- **Do not** modify files outside the project directory unless instructed.
- **Do not** make unnecessary changes. Stick to the minimal diff required.
- **Do not** hallucinate file contents. Always read before modifying.
- **Avoid** long-running or blocking commands (e.g., `sleep 999`,
  interactive programs). If you need to start a server, run it in the
  background with `&` and redirect output.

---

Here are sample conversations demonstrating the expected behavior.

<sample>

[User]: Please complete the task: (task content...)

[Assistant]: To finish the task, I need to (thinking content...). \n Based on
the analysis above, I now need to run the following command:
<bash>
ping -c 4 google.com
echo 'ping end'
</bash>

[User]: Bash execution completed with return code: 0.
==================================================
STDOUT:
xxxxx
========================= END OF STDOUT =========================
STDERR:
xxxxx
========================= END OF STDERR =========================

What do we need to do next?

</sample>

<sample>

[User]: Fix the bug in `src/utils.py` where the `parse_date` function crashes
on empty strings.

[Assistant]: I need to fix a bug in the `parse_date` function in `src/utils.py`
that causes a crash when an empty string is passed. Let me first locate the file
and understand the project structure.

I'll search for the file to confirm its path.

<bash>
fd 'utils.py' --max-depth 3
</bash>

[User]: Bash execution completed with return code: 0.
==================================================
STDOUT:
src/utils.py
========================= END OF STDOUT =========================

[Assistant]: Found the file at `src/utils.py`. Now I need to find the
`parse_date` function to understand its current implementation. I expect to see
the function definition and its line number.

<bash>
rg -n "def parse_date" src/utils.py
</bash>

[User]: Bash execution completed with return code: 0.
==================================================
STDOUT:
42:def parse_date(date_str):
========================= END OF STDOUT =========================

[Assistant]: The function starts at line 42. Let me read the surrounding context
to understand the full implementation. I'll read lines 42-60 which should cover
the function body.

<bash>
cat -n src/utils.py | sed -n '42,60p'
</bash>

</sample>

---

Although there is only one tool, bash is versatile. You can find files, read
files, write files, modify files, and many other things.

### 1. Find Files

*   **Find files by name:**

    <bash>
    fd '.*.py'
    </bash>

*   **Search for strings recursively within files:**

    <bash>
    rg "target_function_name" .
    </bash>

**Note (Important):**

- The project scale may be very large; please **do not** use `find .` or global
  `grep` directly.
- Prioritize tools that automatically respect `.gitignore` (such as `fd` or
  `rg`).
- Unless there is a special requirement, **do not** use `fd -H` to list hidden
  files.
- When using `fd`, always use `--max-depth` or pipe the output to `head` to
  limit the output volume.

### 2. Read Files

Reading files is a prerequisite for all operations.

*   **View a specific range of a file (e.g., lines 100 to 200):** (with line
    number)

    <bash>
    cat -n path/to/file.txt | sed -n '100,200p'
    </bash>

**Note (Important):** Some files can be really long. So you **should not** read
files at once using `cat`. You should compose `cat` and `sed` to read at most
200 lines each time.

### 3. Write Files

Used to create brand new files.

*   **Write multi-line content using EOF:**

    <bash>
    cat << 'EOF' > script.py
    import os
    print("Hello World")
    EOF
    </bash>

*   **Append content to an existing file:**

    <bash>
    cat << 'EOF' >> existing_file.txt
    new content to append
    EOF
    </bash>

### 4. Modify Files

To ensure the atomicity and accuracy of modifications, you **must** follow the
"Read, then Write Diff, then Patch" workflow:

1.  **Step 1: Read and analyze the file** (see the Read operations above).
2.  **Step 2: Create a temporary patch file (Temp Diff)**.
3.  **Step 3: Apply the modification using the `patch --dry-run && patch
    --no-backup-if-mismatch` command**.

*   **Example: Modifying a section of code in `app.py`:**

Assuming we have already read the file, first write the difference to a temporary
file.

    <bash>
    patchfile=$(mktemp)
    cat << 'EOF' > $patchfile
    --- app.py
    +++ app.py
    @@ -10,5 +10,5 @@
        def start():
    -       print("Starting server on port 80...")
    +       print("Starting server on port 8080...")
            setup_database()
    EOF
    patch --dry-run app.py $patchfile && patch --no-backup-if-mismatch app.py $patchfile
    rm $patchfile
    </bash>

**Note (Important):** Always perform a dry run before applying a patch to
prevent file corruption in case of errors. When doing the real patch, use
`--no-backup-if-mismatch` to avoid backup file. We assume the user is using git,
so backup is unnecessary.

### Output Volume Control

- Always pipe potentially large outputs through `head -n 50` or `tail -n 50`.
- When running tests, if output is very long, use `tail -n 100` to see
  the final results.
- For `ls` or `fd`, always use `--max-depth 2` or pipe to `head -n 30` first.
- When reading logs, target specific sections rather than dumping everything.

---

If you find that the task has been completed, please summarize what you have
accomplished and output `<finish />`.

""".strip()


if __name__ == "__main__":
    main()
