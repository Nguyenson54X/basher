import os
from openai import OpenAI

ENDPOINT = os.environ.get("BASHER_API_ENDPOINT", "https://openrouter.ai/api/v1/")
APIKEY = os.environ.get("BASHER_API_KEY")
MODEL = os.environ.get("BASHER_MODEL", "openai/gpt-4o-mini")
PROMPTS_PATH = os.environ.get("BASHER_PROMPTS_PATH")

g_prompts = dict()
g_ctx = list()


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
    # todo: 从s中提取'<bash></bash>'之间的命令，返回值是 ret, err
    # 如果成功，err是None,ret是字符串，里面是提取出来的命令；否则err是错误信息
    # 如果什么bash命令都没有，那么err的信息是：找不到可以执行的bash命令，请给出bash命令
    # 如果有超过一个以上的bash段，那么err的信息是：一次智能执行一个脚本，请给出单个bash脚本段

    import re

    # 查找所有<bash>...</bash>标签之间的内容
    pattern = r"<bash>(.*?)</bash>"
    matches = re.findall(pattern, s, re.DOTALL)

    if len(matches) == 0:
        return None, "找不到可以执行的bash命令，请给出bash命令"
    elif len(matches) > 1:
        return None, "一次智能执行一个脚本，请给出单个bash脚本段"
    else:
        return matches[0].strip(), None


def main():
    load_prompts()
    add_sys_content(g_prompts["core"])
    add_user_content("分析项目，编写AGENTS.md")
    print(g_ctx)
    # run_llm(g_ctx)


if __name__ == "__main__":
    main()
