# GLaDOS Checkin v2.0

[![GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Actions](https://img.shields.io/badge/GitHub%20Actions-Running-success.svg)](https://github.com/wyhc7/Glados_checkin/actions)

GLaDOS 自动签到脚本 — 模块化重构版。每天自动签到获取积分，支持多账号、多渠道推送、指数退避重试。

---

## 功能

- 多账号签到（Cookie 用 & 分隔）
- 智能积分兑换：**到期前 7 天**才触发，自动选能换到的**最长天数**
- 6 渠道推送：Telegram / Bark / Server酱 / PushPlus / 企业微信 / 飞书
- 双层重试（urllib3 + 应用层指数退避），签到/兑换不重复提交
- Cookie 失效单独识别，日志明确提示重抓
- 北京时间日志，Emoji 标注每一步
- GitHub Actions 定时运行 + 手动触发
- 本地 --local / --dry-run 模式
- 完整 pytest 单元测试

---

## 快速开始

### GitHub Actions（推荐）

1. Fork 本仓库
2. Settings → Secrets and variables → Actions → New repository secret

| Secret | 值 | 必填 |
|---|---|---|
| `GLADOS_COOKIES` | Cookie（多账号用 & 分隔） | 是 |
| `GLADOS_EXCHANGE_MIN_DAYS` | 剩余天数低于此值才兑换，默认 `7` | 否 |
| `GLADOS_DOMAINS` | 自定义域名，默认 `glados.cloud` | 否 |
| `GLADOS_PUSH_CHANNEL` | telegram / bark / serverchan / pushplus / wecom / feishu | 否 |
| `GLADOS_PUSH_TOKEN` | 对应渠道 Token | 否 |
| `GLADOS_VERBOSE` | `1` 输出调试日志 | 否 |
| `GLADOS_RETRY_MAX` | 重试次数，默认 `3` | 否 |
| `GLADOS_RETRY_BACKOFF` | 重试退避基数，默认 `2.0` | 否 |

> 除 `GLADOS_COOKIES` 外全部可不填，走默认值。

3. Actions → GLaDOS Auto Checkin v2 → Run workflow 手动测试

默认每天北京时间 **8:00** 和 **14:00** 自动运行。

### 本地运行

```bash
cp .env.example .env   # 编辑填入 GLADOS_COOKIES
pip install -r requirements.txt
python -m src.main --local
```

---

## 获取 Cookie

1. 登录 [GLaDOS](https://glados.cloud) 签到页面
2. F12 → Network → 刷新
3. 点击第一个请求 → Request Headers → Cookie
4. 复制会话部分（**两种前缀都支持，按你账号实际的来**）：
   - `koa:sess=...; koa:sess.sig=...`（老版后端）
   - `gld:sess=...; gld:sess.sig=...`（新版后端）

多账号：`cookie1&cookie2&cookie3`

> **必须带上 `.sig` 那一段。** 只有 `xxx:sess` 没有 `xxx:sess.sig`，
> GLaDOS 一律返回 `code=-2 没有权限`。

---

## 积分兑换

### 规则

**只在剩余天数 < `GLADOS_EXCHANGE_MIN_DAYS`（默认 7 天）时才兑换，且一次换成积分能负担的最长天数。**

不做多次兑换，剩余积分留着下次用。

### 可兑换计划

| 计划 | 需积分 | 兑换天数 | 性价比 |
|---|---|---|---|
| plan100 | 100 | 10 天 | 0.100 天/分 |
| plan200 | 200 | 30 天 | 0.150 天/分 |
| plan500 | 500 | 100 天 | 0.200 天/分 |

plan500 最划算，所以积分够就优先换它。

### 选择示例

| 剩余天数 | 持有积分 | 实际动作 |
|---|---|---|
| 127 天 | 64 | 跳过（还没到期） |
| 34 天 | 141 | 跳过（还没到期） |
| 7 天 | 任意 | 跳过（刚好等于门槛） |
| 6 天 | 900 | 换 plan500（500 分 / 100 天，剩 400 分） |
| 6 天 | 450 | 换 plan200（200 分 / 30 天，剩 250 分） |
| 6 天 | 150 | 换 plan100（100 分 / 10 天，剩 50 分） |
| 6 天 | 50 | 无法兑换（不足最低 100 分） |

### 调整触发时机

想让它在到期前 5 天或 10 天就兑换，改这个：

```
GLADOS_EXCHANGE_MIN_DAYS=5
```

---

## 推送配置示例

### Telegram
```
GLADOS_PUSH_CHANNEL=telegram
GLADOS_PUSH_TOKEN=bot123:abc@123456
```
BotFather 创建机器人获取 token，@后为 chat_id。

### Bark (iOS)
```
GLADOS_PUSH_CHANNEL=bark
GLADOS_PUSH_TOKEN=your_api_key
```

### Server酱
```
GLADOS_PUSH_CHANNEL=serverchan
GLADOS_PUSH_TOKEN=SCT123456
```

### PushPlus
```
GLADOS_PUSH_CHANNEL=pushplus
GLADOS_PUSH_TOKEN=your_token
```

### 企业微信
```
GLADOS_PUSH_CHANNEL=wecom
GLADOS_PUSH_TOKEN=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
```

### 飞书
```
GLADOS_PUSH_CHANNEL=feishu
GLADOS_PUSH_TOKEN=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

---

## 域名

默认 `glados.cloud`，一般不用配。实测可用域名：

| 域名 | 状态 |
|---|---|
| `glados.cloud` | ✅ 默认 |
| `glados.one` | ✅ |
| `glados.network` | ✅ |
| `glados.vip` | ✅ |
| `glados.icu` / `glados.us` / `glados.xyz` / `glados.me` | ❌ 已失效 |

几个可用域名指向同一套服务器，Cookie 通用。

> **别填多个域名。** 任务是 `Cookie 数 × 域名数`，填 3 个域名会让同一账号被签 3 次。

---

## 常见问题

### 报 `code=-2 没有权限` / `Cookie 失效或无权访问`

Cookie 过期或被顶掉了，重新抓一份。

**注意**：在浏览器里打开 F12 控制台会**轮换会话 Cookie**，把你之前存进 Secret 的那份作废。所以抓完 Cookie 后别马上又开控制台。

### 报 `未设置或为空` / `未包含有效 Cookie`

- Secret 名字必须是 `GLADOS_COOKIES`（有 S）
- 值是半角 `;` 和 `&`，不要用中文全角标点
- 检查有没有多余空格或换行

### 日志显示 `🔄 重复签到`

今天已经签过了，正常。第二天会变 `✅ 签到成功`。

### 兑换一直不动

按设计只在剩余 < 7 天时兑换，看日志里的 `跳过兑换（余 N 天，≥7 天不换）`。
想早点兑换就设 `GLADOS_EXCHANGE_MIN_DAYS`。

---

## 项目结构

```
src/
  main.py         入口 + CLI
  api.py          HTTP 客户端（重试、超时、AuthError 识别）
  checker.py      签到编排器 + 兑换计划选择
  config.py       配置管理
  push.py         6 渠道推送
  models.py       数据模型 + 异常
  constants.py    API 端点 / Emoji / 枚举 / 兑换天数
  logging_config.py   北京时间日志
tests/            6 个 pytest 测试文件
.github/workflows/gladosCheck.yml
```

---

## 测试

```bash
pip install -e ".[dev]"
pytest
```

---

## 许可证

GPL-3.0 © 2026 wyhc7
