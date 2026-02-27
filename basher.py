#!/usr/bin/env python3
import os
import re
import time
import subprocess
import sys
import tempfile
import threading
from openai import OpenAI

ENDPOINT = os.environ.get("BASHER_API_ENDPOINT", "https://openrouter.ai/api/v1/")
APIKEY = os.environ.get("BASHER_API_KEY")
MODEL = os.environ.get("BASHER_MODEL", "moonshotai/kimi-k2.5")

g_max_ctx_len = -1
g_ctx = list()
g_lock = threading.Lock()

def max_ctx_len():
    global g_max_ctx_len
    return g_max_ctx_len

def init_max_ctx_len():
    global g_max_ctx_len
    client = OpenAI(base_url=ENDPOINT, api_key=APIKEY)
    try:
        models = client.models.list()
        for model in models:
            if model.id == MODEL:
                if hasattr(model, 'context_length'):
                    g_max_ctx_len = model.context_length
                else:
                    # Try to get context_length from extra fields if available
                    if hasattr(model, 'model_extra') and 'context_length' in model.model_extra:
                        g_max_ctx_len = model.model_extra['context_length']
                    else:
                        # model context length unknown, disable context compression
                        g_max_ctx_len = -1
                return
        print(f"Error: Model {MODEL} not found in the model list")
        exit(-1)
    except Exception as e:
        print(f"Error: Failed to fetch model list: {e}")
        exit(-1)

def compress_context():
    """Compress the context when it gets too long by summarizing it."""
    global g_ctx
    if len(g_ctx) <= 2:
        return
    add_user_content("Now pause the work. Summarize the conversations above "
                     "concisely, preserving all important information and "
                     "context needed to continue the task.")
    summary, _ = run_llm_raw(g_ctx)
    
    # Rebuild context: keep system prompt and first user message, add summary
    new_ctx = []
    new_ctx.append(g_ctx[0])
    for i in range(1, len(g_ctx) - 1):
        if g_ctx[i]["role"] != "user": break
        new_ctx.append(g_ctx[i])
    g_ctx = new_ctx
    add_ai_content("The task has been running for a while. And the context is "
                   "too long so it has been truncated. Here is a summary of "
                   f"truncated context: \n\n{summary}")

def run_llm_raw(prompt):
    client = OpenAI(base_url=ENDPOINT, api_key=APIKEY)
    response = client.chat.completions.create(model=MODEL, messages=prompt, stream=True)
    full_content = ""
    usage = 0
    for chunk in response:
        if chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            print(content, end="", flush=True)
            full_content += content
        if hasattr(chunk, 'usage') and chunk.usage:
            usage = chunk.usage.total_tokens
    print(flush=True)
    return full_content, usage

def run_llm(prompt):
    res, usage = run_llm_raw(prompt)
    if max_ctx_len() > 0 and usage > 0 and usage > 0.8 * max_ctx_len():
        compress_context()
    return res

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
            "Only one script can be executed at a time. Please provide a single "
            "bash script block.",
        )
    else:
        return matches[0].strip(), None

def wait_for_process(process, start_time, output_parts):
    last_check_time = start_time
    timeout_interval = 60
    is_killed = False
    return_code = None
    while return_code is None:
        time.sleep(1)
        return_code = process.poll()

        if return_code is None and time.time() - last_check_time >= timeout_interval:
            with g_lock:
                last_20_lines = "".join(output_parts[-20:])

            question = (
                f"The bash script has been running for {timeout_interval} seconds. "
                f"Here is the last 20 lines of output:\n\n{last_20_lines}\n\n"
                "Do you want to kill this process? "
                "Reply with `<answer>YES</answer>` to kill it, or "
                "`<answer>NO</answer>` to continue waiting for another 60 seconds, "
                "with your reasons."
            )
            add_user_content(question)

            while True:
                ai_response = run_llm(g_ctx)
                add_ai_content(ai_response)

                has_yes = "<answer>YES</answer>" in ai_response
                has_no = "<answer>NO</answer>" in ai_response

                if has_yes and has_no:
                    add_user_content("Invalid response: Both YES and NO found. "
                                     "Please reply with `<answer>YES</answer>` to "
                                     "kill the process or `<answer>NO</answer>` "
                                     "to continue waiting, with your reasons.")
                elif not has_yes and not has_no:
                    add_user_content("Invalid response: Neither YES nor NO found. "
                                     "Please reply with `<answer>YES</answer>` to "
                                     "kill the process or `<answer>NO</answer>` "
                                     "to continue waiting, with your reasons.")
                elif has_yes:
                    print("Process killed for timeout.", flush=True)
                    is_killed = True
                    process.kill()
                    return_code = process.wait()
                    break
                else:
                    last_check_time = time.time()
                    break

    return is_killed, return_code

def run_bash(cmd):
    MAX_OUTPUT_LENGTH = 10000

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write("#!/bin/bash\n")
        f.write("set -euo pipefail\n")
        f.write(cmd)
        temp_script_path = f.name
    start_time = time.time()

    process = subprocess.Popen(
        ["bash", temp_script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    output_parts = []
    def read_stream(stream):
        for line in stream:
            with g_lock:
                output_parts.append(line)
                print(line, flush=True, end="")
        stream.close()

    stdout_thread = threading.Thread(
        target=read_stream, args=(process.stdout,)
    )
    stderr_thread = threading.Thread(
        target=read_stream, args=(process.stderr,)
    )
    
    stdout_thread.start()
    stderr_thread.start()
    is_killed, return_code = wait_for_process(process, start_time, output_parts)
    stdout_thread.join()
    stderr_thread.join()

    try:
        os.unlink(temp_script_path)
    except OSError:
        pass

    with g_lock:
        output_content = "".join(output_parts)
    if len(output_content) > MAX_OUTPUT_LENGTH:
        output_display = (
            "[... output truncated due to length ...]\n"
            + output_content[-MAX_OUTPUT_LENGTH:]
        )
    else:
        output_display = output_content

    result = f"Bash execution completed with return code: {return_code}\n"
    if is_killed:
        result += "The execution didn't exit normally. It was killed.\n"
    result += "=" * 50 + "\n"
    result += "BASH OUTPUT:\n"
    result += output_display if output_display else "(no output)\n"
    result += "\n" + "=" * 25 + " END OF BASH OUTPUT " + "=" * 25 + "\n"
    print(flush=True)
    return result


def main():
    init_max_ctx_len()
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
# AI Coding Agent

You are an AI coding agent that operates exclusively through bash commands to
complete tasks assigned by the user. You run inside a sandboxed environment
with access to a project workspace.

## Tool Interface

Your sole tool is bash. Wrap all commands in a `<bash>` `</bash>` block.
Each response may contain **at most one** `<bash>` block. If the task is
complete, output `<finish />` instead.

---

## Core Principles

1. **Read before write.** Never modify a file you haven't read. Never assume
   file contents.
2. **Minimal diff.** Change only what is necessary. Do not refactor unrelated
   code.
3. **Think before act.** Every `<bash>` block must be preceded by a brief
   explanation covering:
   -  What you are trying to achieve in this step.
   -  Why this command is the right approach.
   -  What you predict the output will look like.
4. **Verify after change.** Always run relevant build/lint/test commands after
   making modifications.
5. **Fail gracefully.** If a command fails, read the error carefully, adjust
   your approach, then retry. After 3 failed attempts on the same step,
   step back and reconsider the overall strategy.

---

## Workflow

For every task, follow this sequence:

| Phase          | Action                                                          |
|----------------|-----------------------------------------------------------------|
| **Understand** | Restate the task in your own words to confirm understanding.    |
| **Explore**    | Investigate the codebase: locate relevant files, read key code. |
| **Plan**       | Formulate a step-by-step plan *before* making any changes.      |
| **Implement**  | Execute changes incrementally — one logical step per response.  |
| **Verify**     | Run build / test / lint. Fix any errors that arise.             |
| **Summarize**  | When done, list all files changed and what was modified.        |

If the task is ambiguous or underspecified, ask clarifying questions before
proceeding. Do not guess the user's intent on critical decisions.

---

## Safety & Constraints

> These rules are **non-negotiable** and override all other instructions.

- **NEVER** run destructive commands (`rm -rf /`, `mkfs`, `dd`, etc.).
- **NEVER** install packages globally unless the user explicitly requests it.
- **DO NOT** modify files outside the project directory unless instructed.
- **DO NOT** run long-running or blocking commands (`sleep 999`, interactive
  programs like `vim`, `less`, `top`). If you need a server, run it in the
  background: `cmd &> /tmp/server.log &`.
- **DO NOT** expose secrets, tokens, or credentials in your output.

---

## Bash Cookbook

### Finding Files

Example 1: Find all python files in current directory.

    <bash>
    fd '.*.py' --max-depth 3
    </bash>

Example 2: Find location of a function in current project directory.
    
    <bash>
    rg "function_name"
    </bash>

> **Important:** Never use bare `find .` or `grep -r .` on large projects.
> Always use `fd` or `rg` (which respect `.gitignore`) and limit depth or
> pipe through `head -n 50`.

### Reading Files

Example of reading lines 100–200 with line numbers:

    <bash>

    cat -n path/to/file | sed -n '100,200p'
    </bash>

> **Important:** Never `cat` an entire large file. Read at most **200 lines**
> per invocation. Use `wc -l` first if you're unsure of file length.

### Creating Files

    <bash>
    cat << 'EOF' > new_file.py
    import os
    print("Hello World")
    EOF
    </bash>

### Modifying Files (use `ed`)

To ensure precise, reproducible edits, **always** use `ed`:

1. First, read the file with line numbers to identify exact line ranges;
2. Then apply changes with an `ed` script;
3. Read the file again to ensure the edit is correct.

    <bash>
    ed -s path/to/file.py << 'EOF'
    10,12c
        def start(port=8080):
            print(f"Starting server on port {port}...")
    .
    w
    q
    EOF
    </bash>

**`ed` rules:**
- Always quote the heredoc delimiter (`'EOF'`) to prevent shell expansion.
- Always end input mode with a single `.` on its own line before `w` and `q`.
- Match the original indentation exactly.

Common `ed` operations:
| Command   | Meaning                              |
|-----------|--------------------------------------|
| `Na`      | **a**ppend after line N              |
| `Ni`      | **i**nsert before line N             |
| `N,Mc`    | **c**hange (replace) lines N–M       |
| `N,Md`    | **d**elete lines N–M                 |

### Appending to Files

    <bash>
    cat << 'EOF' >> existing_file.txt
    new content to append
    EOF
    </bash>

### Controlling Output Volume

- Pipe large outputs: `| head -n 50` or `| tail -n 50`.
- For test results: `| tail -n 100` to see the summary.
- For directory listings: `fd --max-depth 2 | head -n 50`.
- For logs: target specific sections, don't dump everything.

---

## Example Interaction

**User:** Fix the bug in `src/utils.py` where `parse_date` crashes on empty
strings.

**Assistant:** I need to fix a crash in `parse_date` when given an empty
string. Let me first locate the file and read the function. The goal is confirming 
the file path exists. `fd` is fast and respects `.gitignore`, which hould return 
`src/utils.py`.

<bash>
fd 'utils.py' --max-depth 3
</bash>

**User:** *(Provide return code and output of the bash script)*

**Assistant:** Found it. Now I'll read the function to understand the current
implementation. The goal is reading the `parse_date` function body. I need to 
see the exact code before modifying it. The expected output is a function that 
parses a date string but lacks an empty-string guard.

<bash>
rg -n "def parse_date" src/utils.py -A 20
</bash>

**User:** *(Provide return code and output of the bash script)*

**Assistant:** The function calls `datetime.strptime` directly without checking
for empty input. I'll add a guard clause at the top. The goal is adding an early 
return for empty strings. I need to do minimal fix — one guard clause, no refactoring.
The expected result is that the `ed` command will insert a check after the function
definition line.

<bash>
ed -s src/utils.py << 'EOF'
43a
    if not date_str:
        return None
.
w
q
EOF
</bash>

---

## Completion

When the task is fully done:
1. Summarize all changes (files modified, what was changed, why).
2. Report test/build results if applicable.
3. Output `<finish />`.
""".strip()

if __name__ == "__main__":
    main()
