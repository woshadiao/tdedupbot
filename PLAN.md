# 查重 Bot 设计

## 目标与范围

查重 bot 独立运行，监控配置的审稿群。收到主 bot 发布的新投稿时计算内容指纹；发现相似内容后，在该消息下回复 `⚠️ 疑似重复`。标记只供审稿人参考，不改变投稿或审核流程。

一个进程可以监控多个审稿群和多个主 bot。所有群使用同一数据库和内存基线，因此重复标记可以引用另一审稿群的首次出现消息。基线由 bot 收到的投稿及数据库中已有的指纹组成。

## 消息识别

仅处理新消息、配置的审稿群，以及 `from_user.id` 属于 `main_bot_ids` 的消息。主 bot 的回复消息和带 inline keyboard 的消息不视为投稿。

媒体消息检查照片、视频、GIF、贴纸或文件。媒体 caption 不参与文本查重，也不存入文本基线。没有媒体的纯文本消息参与文本查重。

同一媒体组（同群且 `media_group_id` 相同）内的条目属于同一投稿，彼此命中时不标记，也不写入新行；其 `file_unique_id` 仍加入缓存并指向最早命中行。

## 指纹与匹配

| 内容                  | 指纹                                    | 匹配                                                   |
|-----------------------|-----------------------------------------|--------------------------------------------------------|
| 照片                  | 64 位 pHash                             | 汉明距离不超过 `phash_threshold`                       |
| 视频、GIF、贴纸、文件 | 字节 SHA-256                            | 精确匹配                                               |
| 纯文本                | UTF-8 SHA-256、64 位字符 n-gram SimHash | 精确匹配；长度达到 `min_simhash_text_len` 时可近似匹配 |

媒体的 `file_unique_id` 命中内存缓存时无需重新下载。未命中时下载文件并计算指纹。图片 pHash 和文本 SimHash 在启动时从数据库载入内存，之后由新写入的行补充；字节和文本精确匹配查询数据库。命中后标记相似度、距离、首次出现时间和可用的消息链接。

## 数据库

数据库 URL 从 `config.json` 的 `db_url` 读取，默认 `sqlite:///data/dedup.db`。`submission_contents` 保持既有字段与索引不变，并新增 `media_group_id`，以便直接读取已有指纹：

| 字段                                                 | 用途                                                     |
|------------------------------------------------------|----------------------------------------------------------|
| `id`                                                 | 行 ID                                                    |
| `submission_key`                                     | 投稿分组键                                               |
| `media_group_id`                                     | 投稿所属媒体组 ID，单条消息为空                          |
| `type`                                               | `photo`、`video`、`gif`、`document`、`sticker` 或 `text` |
| `phash`、`content_hash`、`text_hash`、`text_simhash` | 内容指纹                                                 |
| `file_unique_id`                                     | Bot API 文件缓存键                                       |
| `source_chat_id`、`source_message_id`                | 原投稿位置                                               |
| `submitter_id`                                       | 投稿者 ID，可为空                                        |
| `first_seen_date`                                    | 首次记录时间                                             |

`(source_chat_id, source_message_id, type)` 有唯一索引。只有成功写入数据库的行会加入内存基线和文件缓存。旧数据库启动时会自动补上 `media_group_id` 列；升级前写入的行该字段为空。

## 代码位置

- `src/main.py`：启动、配置检查、消息过滤。
- `src/update`：超级管理员私聊 Git 更新及进程重启。
- `src/bot/__init__.py`：识别投稿、下载、比对、写入和标记。
- `src/config/__init__.py`：读取当前工作目录的 `config.json`。
- `src/database/__init__.py`：模型及数据库操作。
- `src/detect/__init__.py`：相似指纹扫描。
- `src/fingerprint/__init__.py`：指纹算法。

运行方式见 [README.md](README.md)。

## 管理命令

`superadmin` 是用户 ID 数组。数组中的用户可以私聊使用 `/update`；命令支持分支、远端、提交和 `--force` 参数。普通更新要求工作区干净并仅执行快进同步。`--force` 允许硬重置已跟踪文件。有新提交时，bot 显示提交记录并重启。
