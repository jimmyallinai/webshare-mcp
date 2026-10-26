#!/usr/bin/env python3
"""webshare-mcp：把 Webshare 官方 API 包成 MCP 服务（stdio 传输，零依赖）。

用户只需设置环境变量 WEBSHARE_API_KEY（在 Webshare 后台
Dashboard -> Settings -> API Keys 生成），任何支持 MCP 的客户端
（Claude、Cursor 等）即可直接调用这些工具管理自己的 Webshare 账号：
查订阅与套餐、列代理、换 IP、白名单、流量统计、关闭自动续费等。

可选环境变量：
  WEBSHARE_API_BASE   默认 https://proxy.webshare.io（一般不用改）
  WEBSHARE_AUTH_STYLE 默认 token，即 Authorization: Token <KEY>；
                      设为 raw 时直接把 KEY 作为 Authorization 头的值，
                      供某些凭证托管场景使用。

安全默认值：
  - 列代理与查配置时，默认把代理密码与下载 token 打码；
    只有显式传 include_credentials=true 才返回原文。
  - 换 IP 默认 dry_run 预演；刷新列表、删白名单、关自动续费
    都要求显式传 confirm=true。
"""

import json
import os
import sys
import urllib.request
import urllib.error

API_BASE = os.environ.get("WEBSHARE_API_BASE", "https://proxy.webshare.io").rstrip("/")
API_KEY = os.environ.get("WEBSHARE_API_KEY", "")
AUTH_STYLE = os.environ.get("WEBSHARE_AUTH_STYLE", "token")

V2 = API_BASE + "/api/v2"
V3 = API_BASE + "/api/v3"

SECRET_KEYS = {"password", "proxy_list_download_token"}


def api(method, url, body=None):
    """调用 Webshare API，返回 (状态码, 解析后的 JSON 或原文)。"""
    if not API_KEY:
        raise RuntimeError("未设置环境变量 WEBSHARE_API_KEY，请先在 Webshare 后台生成 API key 并填入。")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if AUTH_STYLE == "raw":
        req.add_header("Authorization", API_KEY)
    else:
        req.add_header("Authorization", f"Token {API_KEY}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if not raw:
                return resp.status, {}
            return resp.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw[:500]}
        return e.code, payload


def scrub(obj):
    """递归打码代理凭证字段，避免密码进入模型上下文。"""
    if isinstance(obj, dict):
        return {k: ("***" if k in SECRET_KEYS else scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


def need_confirm(args, action):
    if not args.get("confirm"):
        raise RuntimeError(f"{action} 是写操作，必须显式传 confirm=true 才会执行。")


# ---------------- 工具实现 ----------------

def t_profile(args):
    return api("GET", f"{V2}/profile/")


def t_subscription(args):
    return api("GET", f"{V2}/subscription/")


def t_plan(args):
    plan_id = args.get("plan_id")
    if not plan_id:
        _, sub = api("GET", f"{V2}/subscription/")
        plan_id = sub.get("plan")
    return api("GET", f"{V2}/subscription/plan/{plan_id}/")


def t_list_proxies(args):
    mode = args.get("mode", "direct")
    page_size = int(args.get("page_size", 25))
    status, data = api("GET", f"{V2}/proxy/list/?mode={mode}&page_size={page_size}")
    if not args.get("include_credentials"):
        data = scrub(data)
    return status, data


def t_proxy_config(args):
    status, data = api("GET", f"{V2}/proxy/config/")
    if not args.get("include_credentials"):
        data = scrub(data)
    return status, data


def t_stats(args):
    return api("GET", f"{V2}/stats/aggregate/")


def t_list_replacements(args):
    return api("GET", f"{V3}/proxy/replace/")


def t_replace_proxy(args):
    to_type = args["to_type"]
    key = {"ip_address": "ip_addresses", "ip_range": "ip_ranges",
           "country": "country_codes", "asn": "asn_numbers"}[to_type]
    to_replace = {"type": to_type, key: args["to_values"]}
    with_type = args.get("with_type", "country")
    if with_type == "any":
        replace_with = [{"type": "any", "count": int(args.get("count", 1))}]
    elif with_type == "country":
        replace_with = [{"type": "country", "country_code": args["with_values"][0]}]
    else:
        wkey = {"asn": "asn_numbers", "ip_range": "ip_ranges"}[with_type]
        replace_with = [{"type": with_type, wkey: args["with_values"]}]
    body = {"to_replace": to_replace, "replace_with": replace_with,
            "dry_run": not args.get("execute", False)}
    return api("POST", f"{V3}/proxy/replace/", body=body)


def t_refresh_proxies(args):
    need_confirm(args, "refresh_proxies")
    return api("POST", f"{V2}/proxy/list/refresh/")


def t_list_ip_authorizations(args):
    return api("GET", f"{V2}/proxy/ipauthorization/")


def t_add_ip_authorization(args):
    return api("POST", f"{V2}/proxy/ipauthorization/", body={"ip_address": args["ip_address"]})


def t_delete_ip_authorization(args):
    need_confirm(args, "delete_ip_authorization")
    return api("DELETE", f"{V2}/proxy/ipauthorization/{args['auth_id']}/")


def t_whatsmyip(args):
    return api("GET", f"{V2}/proxy/ipauthorization/whatsmyip/")


def t_cancel_auto_renewal(args):
    need_confirm(args, "cancel_auto_renewal")
    return api("DELETE", f"{V2}/subscription/renewal/")


TOOLS = [
    {"name": "webshare_profile", "handler": t_profile,
     "description": "查看 Webshare 账号资料（id、邮箱、姓名、邮箱验证状态）。",
     "schema": {"type": "object", "properties": {}}},
    {"name": "webshare_subscription", "handler": t_subscription,
     "description": "查看当前订阅：计费周期、是否自动续费、剩余额度积分、是否暂停或限速。",
     "schema": {"type": "object", "properties": {}}},
    {"name": "webshare_plan", "handler": t_plan,
     "description": "查看套餐详情：价格、流量上限、代理数量、每月替换与刷新额度、附加项开关。不传 plan_id 时用当前订阅的套餐。",
     "schema": {"type": "object", "properties": {"plan_id": {"type": "integer"}}}},
    {"name": "webshare_list_proxies", "handler": t_list_proxies,
     "description": "列出代理（地址、端口、国家、城市、ASN、有效性）。默认打码密码，include_credentials=true 才返回原文。",
     "schema": {"type": "object", "properties": {
         "mode": {"type": "string", "default": "direct"},
         "page_size": {"type": "integer", "default": 25},
         "include_credentials": {"type": "boolean", "default": False}}}},
    {"name": "webshare_proxy_config", "handler": t_proxy_config,
     "description": "查看代理配置：国家与 ASN 分配、可替换的国家、ASN 与 IP 段池。默认打码凭证字段。",
     "schema": {"type": "object", "properties": {
         "include_credentials": {"type": "boolean", "default": False}}}},
    {"name": "webshare_stats", "handler": t_stats,
     "description": "查看聚合流量统计：总流量、请求数、成功与失败数、已用国家。",
     "schema": {"type": "object", "properties": {}}},
    {"name": "webshare_list_replacements", "handler": t_list_replacements,
     "description": "查看换 IP 记录与状态（含预演记录）。",
     "schema": {"type": "object", "properties": {}}},
    {"name": "webshare_replace_proxy", "handler": t_replace_proxy,
     "description": "更换代理 IP。默认 dry_run 预演不真正更换，execute=true 才执行并消耗月替换额度（不可逆）。to_type 可选 ip_address、ip_range、country、asn；with_type 可选 country、asn、ip_range、any。",
     "schema": {"type": "object", "required": ["to_type", "to_values"], "properties": {
         "to_type": {"type": "string", "enum": ["ip_address", "ip_range", "country", "asn"]},
         "to_values": {"type": "array", "items": {"type": "string"}},
         "with_type": {"type": "string", "enum": ["country", "asn", "ip_range", "any"], "default": "country"},
         "with_values": {"type": "array", "items": {"type": "string"}},
         "count": {"type": "integer", "default": 1},
         "execute": {"type": "boolean", "default": False}}}},
    {"name": "webshare_refresh_proxies", "handler": t_refresh_proxies,
     "description": "刷新整个代理列表（需要套餐有按需刷新额度）。必须传 confirm=true。",
     "schema": {"type": "object", "properties": {"confirm": {"type": "boolean", "default": False}}}},
    {"name": "webshare_list_ip_authorizations", "handler": t_list_ip_authorizations,
     "description": "列出 IP 白名单（被授权可免密使用代理的公网 IP）。",
     "schema": {"type": "object", "properties": {}}},
    {"name": "webshare_add_ip_authorization", "handler": t_add_ip_authorization,
     "description": "新增一条 IP 白名单。",
     "schema": {"type": "object", "required": ["ip_address"], "properties": {
         "ip_address": {"type": "string"}}}},
    {"name": "webshare_delete_ip_authorization", "handler": t_delete_ip_authorization,
     "description": "删除一条 IP 白名单。必须传 confirm=true。",
     "schema": {"type": "object", "required": ["auth_id"], "properties": {
         "auth_id": {"type": "integer"}, "confirm": {"type": "boolean", "default": False}}}},
    {"name": "webshare_whatsmyip", "handler": t_whatsmyip,
     "description": "查询当前请求方的公网 IP（加白名单前确认用）。",
     "schema": {"type": "object", "properties": {}}},
    {"name": "webshare_cancel_auto_renewal", "handler": t_cancel_auto_renewal,
     "description": "关闭自动续费。注意官方会同时移除已保存的支付方式，套餐可用到当前周期结束。必须传 confirm=true。",
     "schema": {"type": "object", "properties": {"confirm": {"type": "boolean", "default": False}}}},
]

HANDLERS = {t["name"]: t["handler"] for t in TOOLS}


# ---------------- MCP 协议层（stdio，行分隔 JSON-RPC） ----------------

def send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(req):
    method = req.get("method", "")
    rid = req.get("id")
    if method == "initialize":
        proto = (req.get("params") or {}).get("protocolVersion", "2024-11-05")
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": proto,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "webshare-mcp", "version": "0.1.0"}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            {"name": t["name"], "description": t["description"],
             "inputSchema": t["schema"]} for t in TOOLS]}}
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments") or {}
        fn = HANDLERS.get(name)
        if fn is None:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": f"未知工具：{name}"}],
                "isError": True}}
        try:
            status, data = fn(args)
            text = json.dumps({"status": status, "data": data}, ensure_ascii=False, indent=1)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": text}],
                "isError": status >= 300}}
        except Exception as e:  # 工具错误以 isError 返回，不让服务崩溃
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": f"调用失败：{type(e).__name__}: {e}"}],
                "isError": True}}
    if rid is not None:
        return {"jsonrpc": "2.0", "id": rid, "error": {
            "code": -32601, "message": f"不支持的方法：{method}"}}
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            send(resp)


if __name__ == "__main__":
    main()
