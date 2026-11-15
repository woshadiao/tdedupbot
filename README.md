# dedup bot — 查重

独立的 Telegram 查重 bot。它检查审稿群里收到的新投稿，命中时回复 `⚠️ 疑似重复`，由审稿人决定如何处理。一个进程可以监控多个审稿群和多个主 bot，所有群共用查重基线。

投稿消息由配置的主 bot 顶层发送，且没有 inline keyboard。主 bot 的回复消息不参与查重。媒体投稿只检查媒体本身；caption 不参与文本查重。同一媒体组（同群且组 id 相同）内的条目互不标记。纯文本投稿支持精确和近似查重。

## 配置

从仓库根目录的 `config.json` 读取配置。复制 `config.example.json` 并填入实际值；`config.json` 已加入 `.gitignore`。配置值仅从 JSON 读取。

| 字段                   | 用途                                | 默认值                         |
|------------------------|-------------------------------------|--------------------------------|
| `token`                | 查重 bot token                      | 必填                           |
| `reviewer_groups`      | 审稿群 ID 数组                      | 必填                           |
| `main_bot_ids`         | 主 bot 用户 ID 数组                 | 必填                           |
| `superadmin`           | 可私聊使用 `/update` 的用户 ID 数组 | `[]`                           |
| `custom_api`           | Bot API 地址前缀                    | `https://api.telegram.org/bot` |
| `db_url`               | 数据库 URL                          | `sqlite:///data/dedup.db`      |
| `phash_threshold`      | 图片 pHash 距离阈值                 | `8`                            |
| `simhash_threshold`    | 文本 SimHash 距离阈值               | `16`                           |
| `enable_simhash`       | 近似文本查重开关                    | `true`                         |
| `min_simhash_text_len` | 近似文本查重最短长度                | `12`                           |

## 运行

在仓库根目录启动：

```bash
.venv/bin/python -m src.main
```

查重 bot 需要接收审稿群消息并能发送回复。主 bot 用户 ID 可从主 bot 的 `get_me().id` 获取。每个 token 运行一个常驻进程；启动时从现有数据库载入基线，随后为新投稿补充基线。

## `/update`

`superadmin` 中的用户可以私聊 bot 使用 `/update`。命令与 tg-reviewer-bot-v2.1 的实现一致：

```text
/update [-b <branch>|--branch <branch>] [-r <remote-uri>|--remote <remote-uri>] [-c <commit>|--commit <commit>] [-f|--force]
```

默认在当前分支执行快进更新。指定提交时会先拉取目标分支，再快进到该提交；有新提交才显示提交记录并重启。工作区有未提交或未跟踪内容时，普通更新会取消。`--force` 会执行 `git reset --hard`，丢弃已跟踪文件的本地修改。更新需要当前仓库存在 Git 提交和可用的远端。

## 代码

| 路径                          | 用途                                   |
|-------------------------------|----------------------------------------|
| `src/config/__init__.py`      | 配置                                   |
| `src/fingerprint/__init__.py` | 图片 pHash、字节 SHA-256、文本 SimHash |
| `src/database/__init__.py`    | 投稿指纹表及读写                       |
| `src/detect/__init__.py`      | 内存基线和相似度比对                   |
| `src/bot/__init__.py`         | 新消息处理与重复标记                   |
| `src/update`                  | 私聊更新命令                           |
| `src/main.py`                 | 常驻 bot 入口                          |
| `src/tests/`                  | 离线验证脚本                           |

离线验证脚本位于 `src/tests/test_offline.py` 和 `src/tests/test_bot.py`，可从仓库根目录分别运行。设计与数据库字段见 [PLAN.md](PLAN.md)。
