# Hermes Web LLM Bridge

把已经登录的 LLM 网页端通过 CDP 交给 `hermes` agent 使用。相比 API，网页端通常有更好的联网检索、引用和完整回答。

工具不会启动浏览器，也不会处理登录。agent 先启动一个带远程调试端口的 Chromium 并完成登录，本工具通过 `connect_over_cdp` 复用该浏览器、标签页和登录态。

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

本工具不启动浏览器，因此不需要下载 Playwright 自带 Chromium；它连接到你自己启动的 Chrome/Chromium。

## 启动供 agent 使用的浏览器

用独立的 profile 启动 Chromium/Chrome，并开启 CDP：

```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="$env:LOCALAPPDATA\hermes-webllm-profile"
```

Chromium/Edge 同样可用，只改可执行文件路径。必须使用专门的 `--user-data-dir`：新版 Chrome 不允许在默认 profile 上开启远程调试。

然后在这个浏览器里手动登录目标网页端，并保持窗口打开。默认 CDP 地址是 `http://127.0.0.1:9222`，也可以通过 `--cdp-url` 或环境变量 `HERMES_CDP_URL` 指定。

每个 provider 会复用已经打开的对应标签页；没有对应标签页时，会在同一个浏览器里新开一个。

## CLI

默认输出 JSON，进度和错误日志写到 stderr，stdout 只包含机器可读结果：

```powershell
python main.py --provider deepseek --question "今天有哪些 AI 新闻？"
python main.py --provider kimi --question "问题一" --question "问题二"
python main.py --provider qwen --input questions.example.csv --pretty
python main.py --provider deepseek --input questions.example.txt --timeout 600
Get-Content questions.example.txt | python main.py --provider wenxin --input -
python main.py --list-providers --pretty
```

等价入口：

```powershell
python -m webllm --provider deepseek --question "你好"
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--provider` | `deepseek` / `qwen` / `kimi` / `wenxin` / `antafu`，默认 `deepseek`，可用 `HERMES_WEB_PROVIDER` |
| `-q, --question` | 单个问题，可重复 |
| `--input` | `.txt` / `.csv` / `.json`，`-` 表示从 stdin 读取 |
| `--cdp-url` | CDP 地址，默认 `http://127.0.0.1:9222`，可用 `HERMES_CDP_URL` |
| `--timeout` | 单题等待秒数，默认 300 |
| `--delay` | 每题完成后额外等待秒数 |
| `--new-session` | 第一题前新建会话 |
| `--mode` | 会话模式（隐含新建会话）。蚂蚁阿福：`deep_search`（深度搜索）/ `health_qa`（健康问答）/ `report`（报告解读）/ `medicine`（药盒识别），也可直接写中文标签 |
| `--file` | 提问前附加本地文件（图片/PDF），可重复。用于蚂蚁阿福「报告解读」「药盒识别」等上传模式 |
| `--no-sources` | 不抓取引用链接 |
| `--continue-on-error` | 某题失败后继续后面的题 |
| `--close-pages` | 结束时关闭本次新建的标签页（不关闭浏览器） |
| `--answers-out` | 额外追加纯文本答案文件 |
| `--check` | 只做登录/弹窗/UI 健康检查，不提问 |
| `--no-preflight` | 提交前跳过健康检查 |
| `--preflight-timeout` | 等待页面就绪秒数，默认 30 |
| `--wait-human` | 大于 0 时轮询等待人工登录/验证码，而不是立即失败 |
| `--ui-check` | `off` / `warn` / `error`，默认 `warn` |
| `--ui-viewport` | `small` / `large` / `both`，默认 `both` |
| `--ui-diff-threshold` | 覆盖 provider 的像素差异阈值 |
| `--baseline-dir` | 基线目录，默认 `.webllm/baselines` |
| `--screenshots-dir` | 证据/差异图目录，默认 `.webllm/screenshots` |
| `--update-baseline` | 用当前页面覆盖基线 |
| `--no-dismiss-popups` | 只报告弹窗，不尝试关闭 |
| `--popup-error` | `warn` / `error`，剩余弹窗是否阻塞 |
| `--format json\|text` | 默认 JSON；`text` 便于人工查看 |
| `--pretty` | 格式化 JSON |
| `--quiet` | 不输出 stderr 进度 |

### 页面健康检查与视觉基线

每次提问前（每个 provider 首次）会做前置检查，也可以单独运行：

```powershell
python main.py --provider deepseek --check --pretty
python main.py --provider wenxin --check --update-baseline
python main.py --provider deepseek -q "..." --ui-check error --wait-human 120
```

检查内容：

- **页面状态**：`ready` / `loading` / `logged_out` / `captcha` / `rate_limited` / `maintenance`。登录页、验证码、限流会返回对应 `error_code`；默认立即失败，`--wait-human N` 会在 N 秒内轮询等待人工处理。
- **弹窗**：检测可见的 `role=dialog`、modal/popup/guide/overlay 等，默认尝试点击“关闭/我知道了/跳过”等按钮，防止弹窗挡住问答。
- **UI 基线比较**：按小视口 1280x800 和大视口 1920x1080 截图，遮罩动态对话区域后与基线比较像素差异。基线存放在仓库 `.webllm/baselines/<provider>-<viewport>.png`；首次运行自动创建，`--update-baseline` 主动更新；差异图存到 `.webllm/screenshots/`（已 gitignore）。

### JSON 输出

```json
{
  "ok": true,
  "needs_human": false,
  "provider": "deepseek",
  "provider_name": "DeepSeek",
  "session_url": "https://chat.deepseek.com/a/chat/...",
  "elapsed_seconds": 12.345,
  "results": [
    {
      "status": "ok",
      "provider": "deepseek",
      "question": "今天有哪些 AI 新闻？",
      "answer": "……",
      "sources": [
        {
          "url": "https://example.com/article",
          "title": "文章标题",
          "snippet": "文章标题",
          "kind": "citation"
        }
      ],
      "session_url": "https://chat.deepseek.com/a/chat/...",
      "elapsed_seconds": 12.3,
      "captured_by": "copy",
      "new_session": false,
      "warnings": [],
      "error": null,
      "error_code": null,
      "diagnostics": {}
    }
  ]
}
```

- `ok`：所有结果是否成功。
- `captured_by`：`copy`（复制按钮 + 剪贴板）、`text`（页面文本兜底）、`none`。
- `sources`：从最后一个回答 bubble 内提取的外部链接，按 URL 去重；不是所有网页端/回答都有。
- 单题失败时仍会返回该题的 `status: "error"`、`error` 和 `error_code`；`error_code` 见 `login_required` / `captcha_required` / `rate_limited` / `popup_blocking` / `ui_changed` / `answer_not_detected` / `page_not_ready`。默认立即停止，`--continue-on-error` 可继续。
- `needs_human: true` 表示需要人工处理浏览器（登录/验证码等），此时退出码为 `3`。
- 退出码：`0` 全部成功，`1` 运行失败/部分失败，`2` 参数或输入错误，`3` 需要人工介入。

## Python API

```python
from webllm import WebLLMClient, ask

# 单次调用：每次新建 CDP 连接
answer = ask(
    "deepseek",
    "今天有哪些 AI 新闻？",
    cdp_url="http://127.0.0.1:9222",
)
print(answer.answer)
for source in answer.sources:
    print(source.title, source.url)

# agent 常驻进程：复用一个连接和每个 provider 的标签页
with WebLLMClient("http://127.0.0.1:9222") as client:
    first = client.ask("kimi", "问题一")
    second = client.ask("kimi", "问题二")
```

`client.ask_many(provider, questions, options=AskOptions(...))` 返回 `BatchResult`，适合批量任务。

## 输入格式

TXT：每个非空行一个问题。

CSV：有 `question` 列时读取该列，否则读取第一列。

JSON：字符串数组，或 `{"questions": ["...", {"question": "..."}]}`。

单独一行 `__new_session__` 会在下一题前新建会话：

```text
问题一
__new_session__
问题二
```

## Providers

| Provider | CLI 值 | 默认 URL | 适配器 |
| --- | --- | --- | --- |
| DeepSeek | `deepseek` | `https://chat.deepseek.com/` | `webllm/providers/deepseek.py` |
| 千问 | `qwen` | `https://www.qianwen.com/` | `webllm/providers/qwen.py` |
| Kimi | `kimi` | `https://www.kimi.com/` | `webllm/providers/kimi.py` |
| 文心一言 | `wenxin` | `https://wenxin.baidu.com/` | `webllm/providers/wenxin.py` |
| 蚂蚁阿福 | `antafu` | `https://chat.antafu.com/` | `webllm/providers/antafu.py` |

各网页端已经拆成独立适配器。通常只需要改对应文件的 `ProviderSpec`（URL、输入框、停止按钮、回答容器、复制按钮、来源选择器）。如果某个网页端需要特殊逻辑，直接覆盖 `WebProvider` 的方法，例如：

```python
class DeepSeekProvider(WebProvider):
    spec = DEEPSEEK_SPEC

    def extract_sources(self, page):
        # 针对该网页端的引用面板做额外抓取
        return super().extract_sources(page)
```

新增 provider 时，在 `webllm/providers/` 新建适配器，并在 `webllm/providers/__init__.py` 注册。

## 行为与限制

- 浏览器必须保持可见：回答通过点击复制按钮并读取剪贴板获取；失败时回退到回答容器的 `inner_text`。
- 回答轮询优先等待“停止生成”按钮消失，找不到时回退为等待 DOM 停止变化。
- 联网检索是否开启取决于网页端标签页的当前状态；本工具不会自动切换搜索开关。
- DeepSeek 每次提问前会检测“深度思考”开关，未开启时自动开启（无法定位开关时不阻塞提问）。
- 复用标签页或新开标签页时，某些站点（如 DeepSeek）会短暂跳到登录页再恢复会话；前置检查会等待最多 `--preflight-timeout` 秒。
- 页面健康检查会在提交前自动关掉阻塞弹窗；如果弹窗反复出现，可用 `--popup-error error` 让它变成阻塞错误。
- UI 基线比较会临时把视口切换到配置的尺寸再恢复；动态对话区域通过 provider 的 `dynamic_selectors` 遮罩，减少噪声。
- 来源抓取是尽力而为，取决于网页端是否在回答容器中渲染链接；DOM 改版时需要更新对应选择器的 `source_selectors`。蚂蚁阿福的学术引用（`[1]` 等）是无链接的 `span.custom-rich-text-refer`，因此 `sources` 通常为空。
- 蚂蚁阿福的模式（深度搜索/健康问答/报告解读/药盒识别）只能在新建会话界面切换；使用 `--mode` 时会先新建会话，再切换模式，然后提问。
- 蚂蚁阿福的「报告解读」「药盒识别」需要上传文件；用 `--file`（可重复）附带图片/PDF，会先切模式再上传，最后连同 `--question` 一起提交。上传后需要输入文字才会启用发送。
- 不自动登录、不绕过 CAPTCHA、限流或其他站点保护。遇到验证请在 CDP 浏览器中手动处理。
- `close_pages` 只关闭本工具新建的标签页，不会关闭 agent 的整个浏览器。
