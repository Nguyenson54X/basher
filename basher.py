import os
import re
import subprocess
import tempfile
import threading
from openai import OpenAI

ENDPOINT = os.environ.get("BASHER_API_ENDPOINT", "https://openrouter.ai/api/v1/")
APIKEY = os.environ.get("BASHER_API_KEY")
MODEL = os.environ.get("BASHER_MODEL", "openai/gpt-4o-mini")
DEFAULT_PROMPTS_PATH = os.path.join(os.path.expanduser("~"), "basher", "prompts")
PROMPTS_PATH = os.environ.get("BASHER_PROMPTS_PATH", DEFAULT_PROMPTS_PATH)

g_prompts = dict()
g_ctx = list()
g_lock = threading.Lock()


def load_prompts():
    if PROMPTS_PATH is None:
        return
    if not os.path.exists(PROMPTS_PATH):
        return
    if not os.path.isdir(PROMPTS_PATH):
        return
    for item in os.listdir(PROMPTS_PATH):
        file_path = os.path.join(PROMPTS_PATH, item)
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    g_prompts[item] = f.read()
            except (IOError, UnicodeDecodeError):
                continue


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
            "找不到可以执行的bash命令，请给出bash命令。如果你发现任务已经完成，请总结你完成的内容。并输出`<finish />`",
        )
    elif len(matches) > 1:
        return None, "一次智能执行一个脚本，请给出单个bash脚本段"
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
    result += '\n' + "=" * 25 + ' END OF STDOUT ' + '=' * 25 + "\n"
    result += "STDERR:\n"
    result += stderr_display if stderr_display else "(no output)\n"
    result += '\n' + "=" * 25 + ' END OF STDERR ' + '=' * 25 + "\n"

    return result


def main():
    load_prompts()
    add_sys_content(g_prompts["core"])
    add_user_content("分析项目，编写一个总结文件: BASHER.md")
    while True:
        res = run_llm(g_ctx)
        if "<finish />" in res:
            exit(0)
        cmd, err = extract_bash_cmd(res)
        add_ai_content(res)
        if err is not None:
            add_user_content("格式不对：" + err)
        else:
            res = run_bash(cmd)
            if res is not None:
                print(res)
                add_user_content(res + '\n\n接下来做什么？')


if __name__ == "__main__":
    main()
