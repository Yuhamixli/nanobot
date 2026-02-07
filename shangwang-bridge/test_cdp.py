"""Quick test: check if Avic.exe CDP port is reachable."""
import json
import urllib.request

CDP_URL = "http://127.0.0.1:9222/json"

try:
    r = urllib.request.urlopen(CDP_URL, timeout=3)
    pages = json.loads(r.read())
    print(f"CDP 可用! 找到 {len(pages)} 个页面:")
    for p in pages:
        ptype = p.get("type", "?")
        title = p.get("title", "")
        url = p.get("url", "")[:80]
        ws = p.get("webSocketDebuggerUrl", "")[:80]
        print(f"  [{ptype}] {title}")
        print(f"    url: {url}")
        print(f"    ws:  {ws}")
        print()
except Exception as e:
    print(f"CDP 不可用: {e}")
    print()
    print("请按以下步骤操作:")
    print("1. 先关闭当前运行的 Avic.exe (商网办公)")
    print("2. 用以下命令重新启动:")
    print()
    print('   & "C:\\Program Files (x86)\\AVIC Office\\Avic.exe" --remote-debugging-port=9222')
    print()
    print("3. 登录商网办公后，重新运行此测试")
