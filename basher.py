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
MODEL = os.environ.get("BASHER_MODEL", "openai/gpt-4o-mini")

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

    print()
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
            "No executable bash commands found. Please provide a bash command. If you find the task has already been completed, please summarize what you have done and output <finish />.",
        )
    elif len(matches) > 1:
        return (
            None,
            "Only one script can be executed at a time. Please provide a single bash script block.",
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

    return result


def main():
    add_sys_content(sys_prompt())

    agents_md_path = os.path.join(os.getcwd(), "AGENTS.md")
    if os.path.isfile(agents_md_path):
        with open(agents_md_path, "r", encoding="utf-8") as f:
            agents_content = f.read()
        add_user_content("\nHere is the context infomation about this project:\n\n" + agents_content)

    if len(sys.argv) < 2:
        print("Error: Please provide a task description.")
        print("Usage: " + sys.argv[0] + " <task_description>")
        sys.exit(1)

    add_user_content(" ".join(sys.argv[1:]))
    while True:
        res = run_llm(g_ctx)
        if "<finish />" in res:
            exit(0)
        cmd, err = extract_bash_cmd(res)
        add_ai_content(res)
        if err is not None:
            add_user_content("Format error: " + err)
        else:
            res = run_bash(cmd)
            if res is not None:
                print(res)
                add_user_content(res + "\n\nWhat do we need to do next?")


def sys_prompt():
    return """
You are an AI Agent capable of running bash commands within this environment to complete the tasks assigned to you by the user.

The only tool you can call is bash. The bash scripts are wrapped in a `<bash>` `</bash>` block. For your each output, only one <bash> block can be give.

here is a sample conversation.

<sample>

[User]: Please complete the task: (task content...)

[Assistant]: To finish the task, I need to (thinking content...). \n Based on the analysis above, I now need to run the following command:
<bash>
ping -c 4 google.com
echo 'ping end'
</bash>

<|User|>: The bash return code is 0.

stdin output:

```
xxxxx
```

stdout output:

```
xxxxx
```

What do we need to do next?

</sample>

Although there is only one tool, bash is versatile. You can find files, read files, write files, and modify files.

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

The project scale may be very large; please **do not** use `find .` or global `grep` directly.
Prioritize tools that automatically respect `.gitignore` (such as `fd` or `rg`).
Unless there is a special requirement, **do not** use `fd -H` to list hidden files.
When using `fd`, always use `--max-depth` or pipe the output to `head` to limit the output volume.

### 2. Read Files

Reading files is a prerequisite for all operations.

*   **View a specific range of a file (e.g., lines 100 to 200):**

    <bash>
    sed -n '100,200p' path/to/file.txt
    </bash>

*   **View the beginning and end of a file:**

    <bash>
    head -n 50 file.txt
    echo '---'
    tail -n 50 file.txt
    </bash>

### 3. Write Files

Used to create brand new scripts or configuration files.

*   **Write multi-line content using EOF:**

    <bash>
    cat << 'EOF' > script.py
    import os
    print("Hello World")
    EOF
    </bash>

### 4. Modify Files

To ensure the atomicity and accuracy of modifications, **direct use of `sed -i` for blind replacement is prohibited**. Please follow the "Read, then Write Diff, then Patch" workflow:

1.  **Step 1: Read and analyze the file** (see the Read operations above).
2.  **Step 2: Create a temporary patch file (Temp Diff)**.
3.  **Step 3: Apply the modification using the `patch` command**.

*   **Example: Modifying a section of code in `app.py`:**

Assuming we have already read the file, first write the difference to a temporary file `diff.patch`:

    <bash>
    patchfile=$(mktemp)
    cat << 'EOF' > $patchfile
    --- app.py
    +++ app.py
    @@ -10,5 +10,5 @@
        def start():
    -    print("Starting server on port 80...")
    +    print("Starting server on port 8080...")
            setup_database()
    EOF
    patch app.py $patchfile
    rm $patchfile
    </bash>

---

If you find that the task has been completed, please summarize what you have accomplished and output `<finish />`.
""".strip()


if __name__ == "__main__":
    main()
