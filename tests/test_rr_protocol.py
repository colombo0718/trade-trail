"""
RR postMessage 協定整合測試

模擬 RR 平台作為父框架，驗證 index.html 的 postMessage 通訊行為是否符合協定：
  questInfo → gameInfo + reward_state（初始）
  action    → reward_state（每步）
  pause     → 不送 reward_state
  accel     → toggle（無回傳）

執行方式：
  cd c:/Users/USER/TradeTrail
  python tests/test_rr_protocol.py
"""

import asyncio
import json
import sys
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from playwright.async_api import async_playwright

# ── 設定 ──────────────────────────────────────────────────
LIVE_URL = "https://tradetrail.leaflune.org/"
PORT     = 8765
BASE_DIR = Path(__file__).parent.parent
TIMEOUT  = 15_000   # ms（live 站抓 JSON 可能慢一點）
SESSION  = 42

USE_LIVE = "--live" in sys.argv

# ── 本地 HTTP 伺服器（local 模式才用）─────────────────────
class QuietHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)
    def log_message(self, fmt, *args):
        pass

def start_server():
    server = HTTPServer(('localhost', PORT), QuietHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server

# ── Playwright 輔助函式 ────────────────────────────────────

INIT_SCRIPT = """
// 替換 window.parent 為假父框架，攔截 index.html 的 postMessage 輸出
(function() {
    window.__rrQueue = [];
    window.__rrListeners = [];

    const fakeParent = {
        postMessage: function(data, origin) {
            const msg = (typeof data === 'string') ? JSON.parse(data) : data;
            let matched = false;
            window.__rrListeners = window.__rrListeners.filter(function(listener) {
                if (!matched && listener.predicate(msg)) {
                    clearTimeout(listener.deadline);
                    listener.resolve(msg);
                    matched = true;
                    return false;
                }
                return true;
            });
            if (!matched) window.__rrQueue.push(msg);
        }
    };

    Object.defineProperty(window, 'parent', {
        get: function() { return fakeParent; },
        configurable: true
    });
})();
"""

async def send_to_page(page, payload: dict):
    """模擬 RR 送訊息給 index.html（直接 dispatch MessageEvent）。"""
    js_payload = json.dumps(payload)
    await page.evaluate(
        f"window.dispatchEvent(new MessageEvent('message', {{ data: {js_payload} }}))"
    )

async def wait_for_message(page, predicate_js: str, timeout: int = TIMEOUT):
    """等待 index.html 送出符合條件的 postMessage。predicate_js 接受變數 msg。"""
    result = await page.evaluate(f"""
        new Promise(function(resolve, reject) {{
            var deadline = setTimeout(function() {{
                reject(new Error("timeout"));
            }}, {timeout});

            var idx = window.__rrQueue.findIndex(function(msg) {{
                return ({predicate_js});
            }});
            if (idx !== -1) {{
                clearTimeout(deadline);
                resolve(window.__rrQueue.splice(idx, 1)[0]);
                return;
            }}

            window.__rrListeners.push({{
                predicate: function(msg) {{ return ({predicate_js}); }},
                resolve: resolve,
                reject: reject,
                deadline: deadline
            }});
        }})
    """)
    return result

async def drain_queue(page) -> list:
    return await page.evaluate(
        "(function() { var q = window.__rrQueue.slice(); window.__rrQueue = []; return q; })()"
    )

async def wait_for_status(page, contains: str, timeout_s: int = 10):
    for _ in range(timeout_s * 10):
        txt = await page.evaluate(
            "(function() { var el = document.getElementById('status-text'); return el ? el.textContent : ''; })()"
        )
        if contains in txt:
            return txt
        await asyncio.sleep(0.1)
    raise TimeoutError(f"狀態未出現「{contains}」（最後狀態：{txt}）")


# ── 主測試 ────────────────────────────────────────────────
async def run_tests():
    passed = 0
    failed = 0

    def ok(name):
        nonlocal passed
        passed += 1
        print(f"  [PASS] {name}")

    def fail(name, reason=""):
        nonlocal failed
        failed += 1
        detail = f": {reason}" if reason else ""
        print(f"  [FAIL] {name}{detail}")

    if USE_LIVE:
        target_url = LIVE_URL
        server = None
        print(f"目標：{target_url}（正式站）\n")
    else:
        server = start_server()
        target_url = f"http://localhost:{PORT}/index.html"
        print(f"目標：{target_url}（本地）\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=80)
        page = await browser.new_page()
        page.on("pageerror", lambda e: print(f"  [JS ERROR] {e}"))

        await page.add_init_script(INIT_SCRIPT)
        await page.goto(target_url)

        # ── TEST 1：資料載入 ──────────────────────────────
        print("── TEST 1: 資料載入 ─────────────────────────────────")
        try:
            status = await wait_for_status(page, "等待 RR 連線")
            ok(f"資料載入完成（狀態：{status.strip()}）")
        except TimeoutError as e:
            fail("資料載入", str(e))

        # ── TEST 2：questInfo → gameInfo ──────────────────
        print("\n── TEST 2: questInfo → gameInfo ─────────────────────")
        await send_to_page(page, {"type": "questInfo", "sessionId": SESSION})
        await asyncio.sleep(0.3)

        try:
            msg = await wait_for_message(page, "msg.type === 'gameInfo'")
            ok("收到 gameInfo")

            players    = (msg.get("players") or [{}])
            state_info = players[0].get("stateInfo", [])
            action_info = players[0].get("actionInfo", [{}])

            if len(state_info) == 2:
                ok("stateInfo 有 2 個維度")
            else:
                fail("stateInfo 維度", f"期望 2，實際 {len(state_info)}")

            rsi = next((s for s in state_info if s.get("name") == "RSI"), None)
            if rsi and rsi.get("bin") == 10:
                ok("RSI bin=10")
            else:
                fail("RSI bin", str(rsi))

            pos = next((s for s in state_info if "持倉" in (s.get("name") or "")), None)
            if pos and pos.get("bin") is not None:
                ok(f"持倉格數 bin={pos['bin']}")
            else:
                fail("持倉格數 bin", str(pos))

            if (action_info[0].get("level") if action_info else None) == 3:
                ok("actionInfo level=3（買/持/賣）")
            else:
                fail("actionInfo level", str(action_info))

        except Exception as e:
            fail("gameInfo", str(e))

        # ── TEST 3：初始 reward_state ─────────────────────
        print("\n── TEST 3: 初始 reward_state ────────────────────────")
        try:
            msg = await wait_for_message(page, "msg.type === 'reward_state'")
            ok("收到初始 reward_state")

            if msg.get("sessionId") == SESSION:
                ok(f"sessionId={SESSION}")
            else:
                fail("sessionId", f"期望 {SESSION}，實際 {msg.get('sessionId')}")

            state = msg.get("state", [])
            if len(state) == 2:
                ok("state 維度=2")
            else:
                fail("state 維度", f"期望 2，實際 {len(state)}")

            if msg.get("done") == False:
                ok("done=false")
            else:
                fail("done 應為 false")

            rsi_val = state[0] if state else None
            if rsi_val is not None and 0 <= rsi_val <= 100:
                ok(f"RSI={rsi_val:.1f} 在合法範圍")
            else:
                fail("RSI 範圍", str(rsi_val))

        except Exception as e:
            fail("初始 reward_state", str(e))

        # ── TEST 4：action → reward_state ─────────────────
        print("\n── TEST 4: action → reward_state ────────────────────")
        for label, val in [("持有(1)", 1), ("買入(0)", 0), ("賣出(2)", 2)]:
            await drain_queue(page)
            await send_to_page(page, {"type": "action", "action": val})
            try:
                msg = await wait_for_message(page, "msg.type === 'reward_state'")
                state = msg.get("state", [])
                if msg.get("sessionId") == SESSION and len(state) == 2:
                    ok(f"action={label} → reward_state 正確")
                else:
                    fail(f"action={label} reward_state 格式", str(msg))
            except Exception as e:
                fail(f"action={label}", str(e))

        # ── TEST 5：pause 暫停 ────────────────────────────
        print("\n── TEST 5: pause 暫停 ───────────────────────────────")
        await drain_queue(page)
        await send_to_page(page, {"type": "pause"})
        await asyncio.sleep(0.1)
        await send_to_page(page, {"type": "action", "action": 1})
        await asyncio.sleep(0.4)
        q = await drain_queue(page)
        rs = [m for m in q if m.get("type") == "reward_state"]
        if len(rs) == 0:
            ok("pause 期間 action 不產生 reward_state")
        else:
            fail("pause 不應有 reward_state", f"收到 {len(rs)} 個")
        # 解除暫停
        await send_to_page(page, {"type": "pause"})
        await asyncio.sleep(0.1)

        # ── TEST 6：標的切換 ──────────────────────────────
        print("\n── TEST 6: 標的切換 SPY → AAPL ─────────────────────")
        await drain_queue(page)
        await page.click("[data-sym='AAPL']")
        try:
            await wait_for_status(page, "等待 RR 連線", timeout_s=8)
            sym = await page.evaluate("(function(){ return currentSymbol; })()")
            if sym == "AAPL":
                ok("currentSymbol 切換為 AAPL")
            else:
                fail("currentSymbol", f"實際={sym}")
        except Exception as e:
            fail("標的切換", str(e))

        await asyncio.sleep(0.5)
        q = await drain_queue(page)
        types = [m.get("type") for m in q]
        if "gameInfo" in types:
            ok("標的切換後送出 gameInfo")
        else:
            fail("標的切換後應送 gameInfo", str(types))
        if "reward_state" in types:
            ok("標的切換後送出 reward_state")
        else:
            fail("標的切換後應送 reward_state", str(types))

        # ── TEST 7：done=true ─────────────────────────────
        print("\n── TEST 7: done=true（跑完一輪）────────────────────")
        ep_before = await page.evaluate(
            "(function(){ return episodeCount; })()"
        )
        # 把 currentStep 設到接近末尾
        await page.evaluate("""
            (function(){
                var len = activeData.length;
                currentStep = Math.max(0, len - 2);
            })()
        """)
        await drain_queue(page)
        done_seen = False
        for _ in range(6):
            await send_to_page(page, {"type": "action", "action": 1})
            await asyncio.sleep(0.2)
            q = await drain_queue(page)
            for m in q:
                if m.get("type") == "reward_state" and m.get("done") == True:
                    done_seen = True
                    ok("收到 done=true reward_state")
                    break
            if done_seen:
                break
        if not done_seen:
            fail("未收到 done=true")

        # done=true 後，下一個 action 才觸發 resetEnv()（episodeCount 遞增）
        await asyncio.sleep(0.1)
        await send_to_page(page, {"type": "action", "action": 1})
        await asyncio.sleep(0.3)

        ep_after = await page.evaluate("(function(){ return episodeCount; })()")
        if ep_after > ep_before:
            ok(f"episodeCount 遞增（{ep_before} → {ep_after}）")
        else:
            fail("episodeCount 應在 done 後遞增")

        # ── TEST 8：State 配置切換 ────────────────────────
        print("\n── TEST 8: State 配置切換（勾選多指標）──────────────")
        await drain_queue(page)

        # 勾選 KD %K（id=kd_k）
        await page.evaluate("(function(){ document.getElementById('sc-kd_k').click(); })()")
        await asyncio.sleep(0.5)

        q = await drain_queue(page)
        gi = next((m for m in q if m.get("type") == "gameInfo"), None)
        if gi:
            si = (gi.get("players") or [{}])[0].get("stateInfo", [])
            # 應有：RSI + KD%K + 持倉格數 = 3 維
            if len(si) == 3:
                ok("勾選 KD%K 後 stateInfo 變為 3 維")
            else:
                fail("stateInfo 維度", f"期望 3，實際 {len(si)}")
        else:
            fail("State 切換後應送出 gameInfo")

        rs = next((m for m in q if m.get("type") == "reward_state"), None)
        if rs and len(rs.get("state", [])) == 3:
            ok("state 向量長度同步更新為 3")
        else:
            fail("state 向量長度應為 3", str(rs))

        # 取消 RSI（只剩 KD%K + 持倉 = 2 維）
        await drain_queue(page)
        await page.evaluate("(function(){ document.getElementById('sc-rsi').click(); })()")
        await asyncio.sleep(0.5)

        q = await drain_queue(page)
        gi2 = next((m for m in q if m.get("type") == "gameInfo"), None)
        if gi2:
            si2 = (gi2.get("players") or [{}])[0].get("stateInfo", [])
            if len(si2) == 2:
                ok("取消 RSI 後 stateInfo 變為 2 維")
            else:
                fail("stateInfo 維度", f"期望 2，實際 {len(si2)}")
        else:
            fail("State 切換後應送出 gameInfo")

        await asyncio.sleep(1.5)
        await browser.close()

    if server:
        server.shutdown()
    print(f"\n{'='*50}")
    print(f"結果：{passed} PASS / {failed} FAIL")
    print(f"{'='*50}")
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    exit(0 if success else 1)
