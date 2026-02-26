#!/bin/bash

export HTTPS_PROXY=http://192.168.57.7:8118
export HTTP_PROXY=http://192.168.57.7:8118
export NO_PROXY=localhost,127.0.0.1

opencode -m openrouter/moonshotai/kimi-k2.5 run '完成`TASK.md`中的描述的任务。'
telenotify