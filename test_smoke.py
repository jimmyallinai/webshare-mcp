#!/usr/bin/env python3
"""离线自检：启动 server.py，走一遍 initialize 与 tools/list，不访问网络。"""

import json
import subprocess
import sys

EXPECTED_TOOLS = {
    "webshare_profile",
    "webshare_subscription",
    "webshare_plan",
    "webshare_list_proxies",
    "webshare_proxy_config",
    "webshare_stats",
    "webshare_list_replacements",
    "webshare_replace_proxy",
    "webshare_refresh_proxies",
    "webshare_list_ip_authorizations",
    "webshare_add_ip_authorization",
    "webshare_delete_ip_authorization",
    "webshare_whatsmyip",
    "webshare_cancel_auto_renewal",
}


def main():
    proc = subprocess.Popen(
        [sys.executable, "server.py"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )

    def rpc(req):
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())

    init = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05"}})
    assert init["result"]["serverInfo"]["name"] == "webshare-mcp", init

    proc.stdin.write(json.dumps(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()

    tools = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in tools["result"]["tools"]}
    assert names == EXPECTED_TOOLS, f"工具集合不符：{names ^ EXPECTED_TOOLS}"

    proc.stdin.close()
    proc.wait(timeout=10)
    print(f"自检通过：initialize 正常，{len(names)} 个工具齐全。")


if __name__ == "__main__":
    main()
