---
name: claude-account-switch
description: 不重開視窗、不丟上下文，把正在跑的 Claude Code 換成另一個登入帳號，並當場驗證真的換了。額度用完換號、多帳號輪換都用它。
version: 1.0
---

# 切換 Claude Code 帳號

不重開視窗、不丟上下文，把正在跑的 Claude Code 換成另一個登入帳號，並當場驗證真的換了。額度用完換號、多帳號輪換都用它。

標籤：claude、cli、帳號、維運

## 怎麼做（Prompt 技能）


# 不重开会话，切换 Claude Code 登录账号

你的任务：在**不关掉正在运行的 Claude Code 会话**的前提下，把它用的登录账号换成另一个，并**当场验证真的换了**。

适用：同一台机器上有多个 Claude 账号（各自有独立额度），想在跑到一半时切到另一个账号继续，而不想丢掉当前上下文。

## 一、先搞清楚机制（不懂这点会做出「看起来成功、其实没换」的结果）

Claude Code 读的凭据档是 `$HOME/.claude/.credentials.json`。

**关键**：如果进程启动时带了环境变量 `CLAUDE_CONFIG_DIR`，它就改读 `$CLAUDE_CONFIG_DIR/.credentials.json`，
而且**这个变量在进程启动那一刻就固定了，之后改不动**。

⇒ 由此得出两条硬结论：
1. **能热切的前提**：目标进程启动时**没带** `CLAUDE_CONFIG_DIR`。带了的进程，你做什么都切不动它，只能重开。
2. 热切的做法 ＝ 让 `~/.claude/.credentials.json` **指向另一份凭据**，而不是去改任何程序的代码或配置。

## 二、准备：把每个账号的凭据各自存一份

给每个账号建一个独立目录，各自登录一次，凭据就会落在各自目录里：

```bash
mkdir -p ~/.claude-accounts/accountA ~/.claude-accounts/accountB
chmod 700 ~/.claude-accounts ~/.claude-accounts/*

# 对每个账号各做一次：用独立目录跑一次登录，登完凭据就留在那个目录
CLAUDE_CONFIG_DIR=~/.claude-accounts/accountA claude   # 在里面完成登录后退出
CLAUDE_CONFIG_DIR=~/.claude-accounts/accountB claude
```

确认每个目录下都有 `.credentials.json`：

```bash
ls -l ~/.claude-accounts/*/.credentials.json
```

## 三、把 `~/.claude/.credentials.json` 变成软链（只做一次）

⚠️ 它现在可能是**实体档**（你原本登录的那个账号）。**先备份再换**，否则会丢掉现有登录：

```bash
cp -a ~/.claude/.credentials.json ~/.claude/.credentials.json.bak-$(date +%Y%m%d%H%M%S)
ln -sfn ~/.claude-accounts/accountA/.credentials.json ~/.claude/.credentials.json
```

## 四、切换（原子替换，别用「先删再建」）

```bash
ln -sfn ~/.claude-accounts/accountB/.credentials.json ~/.claude/.credentials.json.tmp \
  && mv -Tf ~/.claude/.credentials.json.tmp ~/.claude/.credentials.json
```

用 `mv -T` 是为了**原子替换**：中间没有「档案不存在」的空窗，正在读它的进程不会撞上半截状态。
⛔ 别写成 `rm` 再 `ln`——那中间有一瞬间凭据档不存在，恰好在那一刻读它的进程会失败。

## 五、验证（这一步不做就等于没做）

```bash
# 1. 软链现在指向谁
readlink -f ~/.claude/.credentials.json

# 2. 哪些在跑的进程【切得动】：它的环境里没有 CLAUDE_CONFIG_DIR 才算
for p in $(pgrep -x claude); do
  printf '%s: ' "$p"
  if tr '\0' '\n' < /proc/$p/environ 2>/dev/null | grep -q '^CLAUDE_CONFIG_DIR='; then
    echo "钉死在自己的目录 → 本次切换对它无效，要换只能重开"
  else
    echo "读的是软链 → 已跟着切换"
  fi
done
```

🔴 **报告结果时必须逐个进程说清楚哪些切了、哪些没切**。
只说「已切换」是不够的——一个带了 `CLAUDE_CONFIG_DIR` 的会话会继续用旧账号扣额度，
而表面上一切正常，**只有额度账单会告诉你出了问题**。

## 六、别踩的坑

- **「等下次刷新 token 就会自然切过去」是错的**：带了 `CLAUDE_CONFIG_DIR` 的进程**根本不读**那条软链，等多久都不会切。
- **副作用要讲清楚**：这条软链喂的是这台机器上**所有**没带 `CLAUDE_CONFIG_DIR` 的 Claude 进程。你切一次，它们全都跟着切。
- **换账号前先确认目标目录里装的确实是你以为的那个账号**（别切到一个已经过期或登成别人的目录）。
- **凭据档权限保持 600、目录 700**，别把它们放进任何会被同步或提交的目录。
