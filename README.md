# GLaDOS Checkin v2.0

[![GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Actions](https://img.shields.io/badge/GitHub%20Actions-Running-success.svg)](https://github.com/wyhc7/Glados_checkin/actions)

GLaDOS 自动签到脚本 — 模块化重构版。每天自动签到获取积分，支持多账号、多渠道推送、指数退避重试。

---

## 功能

- 多账号签到（Cookie 用 & 分隔）
- 自动积分兑换（plan100 / plan200 / plan500）
- 6 渠道推送：Telegram / Bark / Server酱 / PushPlus / 企业微信 / 飞书
- 双层重试（urllib3 + 应用层指数退避）
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
| `GLADOS_EXCHANGE_PLAN` | plan100 / plan200 / plan500 | 否 |
| `GLADOS_PUSH_CHANNEL` | telegram / bark / serverchan / pushplus / wecom / feishu | 否 |
| `GLADOS_PUSH_TOKEN` | 对应渠道 Token | 否 |

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

1. 登录 https://glados.cloud 后退出再登录一次（GLaDOS 自 2026-09 起更换会话 Cookie 前缀）
2. F12 → Network → 刷新 → 任一请求 → Request Headers → Cookie
3. 复制完整 Cookie，必须包含 gld:sess 与 gld:sess.sig：
   koa:sess=...; koa:sess.sig=...; gld:sess=...; gld:sess.sig=...

多账号：`cookie1&cookie2&cookie3`

---

## 兑换计划

| 计划 | 需积分 | 兑换天数 |
|---|---|---|
| plan100 | 100 | 10 天 |
| plan200 | 200 | 30 天 |
| plan500 | 500 | 100 天（默认） |

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

## 项目结构

```
src/
  main.py         入口 + CLI
  api.py          HTTP 客户端（重试、超时）
  checker.py      签到编排器
  config.py       配置管理
  push.py         6 渠道推送
  models.py       数据模型 + 异常
  constants.py    API 端点 / Emoji / 枚举
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
