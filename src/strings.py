"""Messages used by the private update command."""

others = {
    "update_usage": "使用方法：`/update [-b <branch>|--branch <branch>] [-r <remote-uri>|--remote <remote-uri>] [-c <commit>|--commit <commit>] [-f|--force]`",
    "update_started": "当前分支：{branch}\n正在拉取更新……",
    "update_dirty": "工作区存在未提交或未跟踪内容，已取消更新。若要丢弃本地修改，请使用 --force。",
    "update_branch_failed": "无法确定当前 Git 分支，请使用 --branch 指定分支。",
    "update_invalid_branch": "指定的 Git 分支名无效。",
    "update_invalid_commit": "指定的 Git commit ID 无效。",
    "update_failed": "更新失败，请检查日志。",
    "update_unchanged": "当前分支：{branch}\n已是最新版本（{commit}），无需重启。",
    "update_details": "当前分支：{branch}\n更新范围：{old_commit} -> {new_commit}\n\n{commits}",
    "update_removed_commits": "回退并移除以下提交：\n{commits}",
    "update_restarting": "Git 同步完成，正在重启。",
    "update_restart_failed": "代码已更新，但自动重启失败，请检查日志并手动重启。",
}
