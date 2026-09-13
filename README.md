# New Movie Tracker

一个 Agent Skill，让 AI 自动监控 sehuatang.org 论坛新作更新。你只需要告诉 AI 喜欢哪些演员，它就会在论坛里筛选这些演员最近发布的作品，并可选提取磁力链接。

## 功能

- **对话式演员管理**：直接口述演员名字，Agent 自动维护追踪清单
- **多板块监控**：默认扫描 `forum-2`（今日下载链接）、`forum-103`（有码）、`forum-37`（资源）
- **智能翻页**：自动翻页并提前停止，避免无效请求
- **磁力提取**：进入帖子详情页自动抓取 `magnet:?xt=urn:btih:` 链接
- **JavDB 补全**：整合 [javdb-cli](https://github.com/zjk1984/javdb-cli) 的 App API，按番号查发行日、标题和磁力（论坛只有 BT 附件时尤其有用）
- **中字优先采集**：论坛中字帖 → JavDB 中字 → 论坛兜底，并可选推送 PikPak **My Pack**
- **内容过滤**：默认保留有码 + 无码 JAV 磁力，排除欧美/FC2/素人
- **Cloudflare 穿透**：复用本地 Chrome 会话，首次验证后自动通行

## 安装

方法一：直接把项目链接给你的ai 

方法二：
克隆到本地即可使用，支持通过 AI Agent 调用，也支持直接运行底层脚本。

```bash
git clone https://github.com/sakana9826/new-movie-tracker-skill.git
cd new-movie-tracker-skill
pip install -r requirements.txt
python -m playwright install
```

> 需要 Windows + Python 3.9+ + Google Chrome。

### 作为 Agent Skill 使用

如果你的 AI Agent 支持读取 `SKILL.md` 指令文件，将本仓库放到 Agent 的技能目录下并启用即可。Agent 会读取 `SKILL.md` 中的指令，自动调用 `scripts/scan.py` 完成扫描。

## 使用方法

### 告诉 AI 你想追踪谁

安装启用后，直接用自然对话告诉你的 AI 演员名单，例如：

> "帮我追踪 佐々木さき、楪カレン、五日市芽依"

> "再加一个 森日向子，删掉 三上悠亜"

> "从我的 D:\Movies\Actors 文件夹导入演员名单"

Agent 会自动维护 `actors.json`，后续扫描都基于这份清单。

### 查询更新

演员清单设置好后，随时问：

- "帮我看看谁更新了"
- "最近三天有谁出新作"
- "sehuatang 上我喜欢的演员有更新吗"
- "扫一下 forum-36 和 forum-103，顺便把磁力链接也拿了"

Agent 会调用 `scripts/scan.py` 运行扫描并返回结果。

### 演员清单的几种维护方式

| 方式 | 示例对话 |
|------|---------|
| **口述添加** | "把 佐々木さき 加进清单" |
| **口述删除** | "删掉 三上悠亜" |
| **文件夹导入** | "从 D:\Movies\Actors 导入演员" |
| **直接编辑** | 修改目录下的 `actors.json` |

### 中日文名称别名

论坛标题可能使用中文名称，而你提供的是日文名称，或者反过来。项目现在支持别名组：

- `actors.json` 继续保存主追踪名单
- `aliases.json` 保存中日文别名映射
- `actors.json` 也可以直接写成 `{ "name": "...", "aliases": [...] }` 的形式

示例：

```json
{
  "aliases": {
    "三上悠亜": ["三上悠亚"]
  }
}
```

扫描时会把主名和别名一起匹配，并在结果里显示实际命中的 `matched_names`。脚本也会自动生成少量安全变体，例如 `々` 展开和常见日式汉字简化。

### 首次运行注意

因为目标网站有 Cloudflare 防护，**第一次运行时会弹出一个 Chrome 窗口**。如果出现人机验证请手动完成（最多等待 90 秒）。验证通过后，会话信息保存在 `chrome_profile/` 中，后续运行无需再次验证。

## 手动运行脚本（不依赖 Agent）

```bash
cd new-movie-tracker

# 基础扫描（使用 actors.json 中的清单）
python scripts/scan.py --days 3

# 扫描并提取磁力链接
python scripts/scan.py --days 3 --fetch-magnets

# 中字优先 + 自动推送 PikPak（推荐）
python scripts/pikpak_login.py login
python scripts/scan.py --days 3 --cnsub-priority --pikpak

# 论坛 + JavDB 双源磁力（推荐 BT 种子帖）
python scripts/scan.py --keyword 流出 --javdb --javdb-magnets --javdb-best --fetch-magnets

# 仅 JavDB 查番号磁力
python scripts/javdb_lookup.py SSIS-589 --magnets --best

# JavDB 登录（可选，匿名查磁力通常已够用）
python scripts/javdb_login.py login
python scripts/javdb_login.py status --check

# 临时指定演员扫描（不保存到清单）
python scripts/scan.py --actors 佐々木さき 楪カレン --days 3 --fetch-magnets

# 从文件夹导入并保存
python scripts/scan.py --actors-dir "D:\Movies\Actors" --save-actors
```

完整参数说明见 [reference.md](reference.md)。

## 目录结构

```
new-movie-tracker/
├── SKILL.md           # Agent 指令文件
├── README.md          # 本文件
├── actors.json        # 演员清单（由 Agent 自维护）
├── aliases.json       # 中日文别名映射
├── reference.md       # 详细参数与排错文档
├── .gitignore
└── scripts/
    ├── scan.py           # 核心扫描脚本
    ├── javdb_client.py   # JavDB App API 客户端
    ├── javdb_lookup.py   # 番号查询 CLI
    ├── javdb_login.py    # JavDB 账号登录
    ├── magnet_select.py  # 中字优先磁力策略
    └── pikpak_download.py
```

## 常见问题

**Q: Chrome 窗口弹出来又关了，没来得及点验证？**  
A: 重新运行即可。如果频繁触发验证，尝试关闭其他 Chrome 窗口后再运行，确保 Playwright 能独占 `chrome_profile`。

**Q: 为什么有些帖子没匹配到？**  
A: 脚本使用「子字符串匹配」。如果论坛标题使用了别名、缩写、或不同假名写法，就会漏掉。可以把中日文名称和常见别名加进 `aliases.json`。

**Q: 匹配到了不相关的帖子？**  
A: 检查 `actors.json` 中是否有过于简短或通用的名字（如 `000`、`fc2` 之类）。直接编辑删除即可。

**Q: 磁力链接提取失败？**  
A: 部分帖子可能使用网盘链接或其他分享方式，没有磁力链。此时结果中会显示 `magnets: (none found)`。

## License

MIT
