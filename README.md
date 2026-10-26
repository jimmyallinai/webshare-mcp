# webshare-mcp

把 [Webshare](https://www.webshare.io/) 官方 API 包成 MCP 服务的零依赖实现。填入你自己的 API key，任何支持 MCP 的客户端（Claude、Cursor 等）都能直接管理你的 Webshare 账号，不用再开网页后台。

## 能做什么

- 查账号、订阅与套餐（周期、自动续费、流量上限、替换与刷新额度）
- 列代理与代理配置（国家、城市、ASN、有效性）
- 看流量统计（总流量、请求数、成功与失败）
- 换 IP（支持按地址、IP 段、国家、ASN 定向，默认预演不真换）
- 刷新整个代理列表（需要套餐有按需刷新额度）
- 管理 IP 白名单（免密使用代理的公网 IP）
- 关闭自动续费

## 快速开始

1. 在 Webshare 后台生成 API key：Dashboard -> Settings -> API Keys。注意 API key 拥有账号的完整权限，请妥善保管，不要提交到任何仓库。

2. 把 key 放进环境变量：

```bash
export WEBSHARE_API_KEY="你的 API key"
```

3. 在你的 MCP 客户端里注册本服务。以 Claude Code 为例：

```bash
claude mcp add webshare -- python3 /path/to/webshare-mcp/server.py
```

其他客户端参照同样的 stdio 配置：命令 `python3`，参数为本仓库 `server.py` 的路径，环境变量带 `WEBSHARE_API_KEY`。

4. 对你的 AI 说一句「列一下我的 Webshare 代理」即可验证。

## 环境变量

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `WEBSHARE_API_KEY` | 是 | 你的 Webshare API key |
| `WEBSHARE_API_BASE` | 否 | API 基础地址，默认 `https://proxy.webshare.io` |
| `WEBSHARE_AUTH_STYLE` | 否 | 默认 `token`（`Authorization: Token <KEY>`）；`raw` 表示直接把 KEY 作为 Authorization 头的值，供凭证托管场景使用 |

## 安全默认值

- 列代理与查配置时默认打码代理密码与下载 token，显式传 `include_credentials=true` 才返回原文。
- 换 IP 默认只做 dry_run 预演，`execute=true` 才真正更换（消耗月替换额度且不可逆，旧 IP 无法找回）。
- 刷新列表、删白名单、关自动续费都要求显式传 `confirm=true`。关自动续费时官方会同时移除已保存的支付方式，请知悉。

## 实现说明

- 纯 Python 标准库实现 MCP 的 stdio 传输（行分隔 JSON-RPC），无需 pip 安装任何依赖，Python 3.10+ 即可运行。
- 接口依据 Webshare 官方 API 文档（https://apidocs.webshare.io/）：账号与订阅走 `/api/v2`，换 IP 走 `/api/v3/proxy/replace/`。
- 本项目与 Webshare 官方无关，是社区实现；官方另有托管 MCP 与 CLI，可在官方文档的 CLI & SDKs 与 MCP Server 页面查看。

## 自检

```bash
python3 test_smoke.py
```

该脚本不访问网络，只验证服务能启动并正确响应 initialize 与 tools/list。

## License

MIT
