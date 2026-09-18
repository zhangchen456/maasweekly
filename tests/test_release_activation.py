"""Task 06 激活协议测试（T04–T06、T15；复验修复 P0b/P1a/P1b 后全套）。

ops/server/maasweekly-activate 以 MAAS_RELEASE_ROOT 注入临时目录；
- 蓝绿服务用 shared/activate-hook 桩模拟（生产 systemd）
- nginx 用 MAAS_NGINX_TEST hook 模拟（记录调用顺序、可注入失败）
- 切换后入口冒烟用 MAAS_SMOKE_URL 注入本地桩入口
flock 并发用例在 macOS 跳过（CI ubuntu 跑）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ACTIVATE = BASE / "ops" / "server" / "maasweekly-activate"
sys.path.insert(0, str(BASE / "pipeline" / "scripts"))
import release_manifest as rm  # noqa: E402

HAS_FLOCK = shutil.which("flock") is not None


def make_release(root: Path, rid: str, git_ts: int, ds: str | None = None) -> Path:
    """构造完整合法 release（含 manifest——走真实 rm.build_manifest）。"""
    d = root / "incoming" / rid
    d.mkdir(parents=True)
    (d / "site").mkdir()
    (d / "site" / "index.html").write_text(f"<html>{rid}</html>")
    src = rid.replace("rl_", "").replace("_", "")
    ds = ds or ("ds_" + (src * 8)[:64])
    (d / "data").mkdir()
    (d / "data" / "manifest.json").write_text(json.dumps({
        "schemaVersion": "1.0", "datasetVersion": ds, "dataThrough": "2026-09-16",
        "coverage": {}, "files": [],
        "retainedVersions": [{"datasetVersion": ds, "generatedAt": "2026-09-16T00:00:00Z"}],
    }))
    (d / "agent-api" / "dist").mkdir(parents=True)
    (d / "agent-api" / "dist" / "server.js").write_text("// stub")
    m = rm.build_manifest(
        d, rid=rid, git_commit="c" * 40, git_ts=git_ts,
        dataset_version=ds, data_through="2026-09-16",
        built_at="2026-09-17T00:00:00Z")
    (d / "metadata").mkdir()
    (d / "metadata" / "release-manifest.json").write_text(json.dumps(m))
    return d


class ActivateFixture(unittest.TestCase):
    """临时 release root + 服务桩 + nginx hook 桩 + 入口冒烟桩。"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="t06-act-"))
        for sub in ("incoming", "releases", "shared/state", "shared/slots",
                    "shared/nginx", "locks"):
            (self.root / sub).mkdir(parents=True)
        # ---- 服务桩：在槽位端口起模拟 status 服务 ----
        hook = self.root / "shared" / "activate-hook"
        hook.write_text(f"""#!/bin/bash
ACTION="$1"; SLOT="$2"; RID="$3"; PORT="${{4:-0}}"
LOG={self.root}/shared/state/hook.log
echo "$ACTION $SLOT $RID $PORT" >> "$LOG"
if [ "$ACTION" = "start" ] && [ "$PORT" != "0" ]; then
  python3 -c "
import http.server, threading, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Length','2'); self.end_headers(); self.wfile.write(b'{{}}')
    def log_message(self, *a): pass
srv = http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), H)
import time
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(120)
" "$PORT" >/dev/null 2>&1 &
  echo $! >> {self.root}/shared/state/hook.pids
fi
exit 0
""")
        hook.chmod(0o755)
        # ---- nginx hook 桩：记录调用顺序；FAIL 文件注入失败 ----
        self.nginx_log = self.root / "shared" / "state" / "nginx.log"
        nginx_hook = self.root / "shared" / "state" / "nginx-hook"
        nginx_hook.write_text(f"""#!/bin/bash
# 模拟 nginx -t / -s reload。FAIL_<step> 文件存在时对应步骤失败
ACTION="$1"; ARG="${{2:-}}"
LOG={self.root}/shared/state/nginx.log
echo "$ACTION $ARG" >> "$LOG"
if [ "$ACTION" = "test" ] && [ -f {self.root}/shared/state/FAIL_nginx_test ]; then
  exit 1
fi
if [ "$ACTION" = "reload" ] && [ -f {self.root}/shared/state/FAIL_nginx_reload ]; then
  exit 1
fi
exit 0
""")
        nginx_hook.chmod(0o755)
        self.smoke_port = 9599  # 不监听——entry_smoke 会失败
        self.env_base = {
            **os.environ,
            "MAAS_RELEASE_ROOT": str(self.root),
            "MAAS_NGINX_TEST": str(nginx_hook),
        }

    def tearDown(self):
        pids = self.root / "shared" / "state" / "hook.pids"
        if pids.exists():
            for pid in pids.read_text().split():
                try:
                    os.kill(int(pid), 9)
                except (ProcessLookupError, ValueError):
                    pass
        shutil.rmtree(self.root, ignore_errors=True)

    def activate(self, *args, expect_rc=0, smoke_url=""):
        env = {**self.env_base, "MAAS_SMOKE_URL": smoke_url}
        r = subprocess.run(["bash", str(ACTIVATE), *args],
                           capture_output=True, env=env, timeout=180)
        r.stdout = r.stdout.decode("utf-8", errors="replace")
        r.stderr = r.stderr.decode("utf-8", errors="replace")
        if expect_rc is not None:
            self.assertEqual(r.returncode, expect_rc,
                             f"rc={r.returncode} stderr={r.stderr[:300]}")
        return r

    def rid(self, ch: str) -> str:
        return "rl_" + ch * 10 + "_" + (chr(ord(ch) + 1)) * 12

    def current(self) -> str:
        r = subprocess.run(["readlink", str(self.root / "current")],
                           capture_output=True, text=True)
        return Path(r.stdout.strip()).name if r.stdout.strip() else ""

    def nginx_calls(self) -> list[str]:
        if not self.nginx_log.exists():
            return []
        return [l.split(" ")[0] for l in self.nginx_log.read_text().splitlines()]

    def effective_inc(self) -> str:
        inc = self.root / "shared" / "nginx" / "agent-upstream.inc"
        return inc.read_text() if inc.exists() else ""


class TestT04Basic(ActivateFixture):

    def test_first_activate(self):
        rid = self.rid("a")
        make_release(self.root, rid, git_ts=1789000000)
        r = self.activate("activate", rid)
        self.assertIn("activated", r.stdout)
        self.assertEqual(self.current(), rid)
        # nginx 被真实调用：test → reload（复验 P0b）
        calls = self.nginx_calls()
        self.assertIn("test", calls)
        self.assertIn("reload", calls)
        self.assertLess(calls.index("test"), calls.index("reload"))
        # 生效 include 绑定新 release：root 与 upstream 同 rid
        inc = self.effective_inc()
        self.assertIn(f"root {self.root}/releases/{rid}/site", inc)
        self.assertIn("upstream agent_api", inc)

    def test_idempotent_same_release(self):
        rid = self.rid("a")
        make_release(self.root, rid, git_ts=1789000000)
        self.activate("activate", rid)
        r = self.activate("activate", rid, expect_rc=0)
        self.assertIn("幂等", r.stdout)

    def test_stale_commit_rejected(self):
        old = self.rid("a")
        new = self.rid("c")
        make_release(self.root, old, git_ts=1789000100)
        make_release(self.root, new, git_ts=1789000000)
        self.activate("activate", old)
        r = self.activate("activate", new, expect_rc=4)
        self.assertIn("旧提交", r.stderr)

    def test_invalid_rid_rejected(self):
        r = self.activate("activate", "rl_$(evil)_x", expect_rc=2)
        self.assertIn("格式非法", r.stderr)

    def test_identity_conflict_rejected(self):
        rid = self.rid("a")
        make_release(self.root, rid, git_ts=1789000000)
        self.activate("activate", rid)
        make_release(self.root, rid, git_ts=1789000000)
        (self.root / "incoming" / rid / "site" / "index.html").write_text("DIFFERENT")
        m = rm.build_manifest(
            self.root / "incoming" / rid, rid=rid, git_commit="c" * 40,
            git_ts=1789000000, dataset_version="ds_" + "1" * 64,
            data_through="2026-09-16", built_at="x")
        (self.root / "incoming" / rid / "metadata" / "release-manifest.json").write_text(
            json.dumps(m))
        r = self.activate("activate", rid, expect_rc=3)
        self.assertIn("身份冲突", r.stderr)


@unittest.skipIf(not HAS_FLOCK, "macOS 无 flock——CI (ubuntu) 跑")
class TestT04Concurrent(ActivateFixture):

    def test_concurrent_activates_serialized(self):
        r1 = self.rid("a")
        r2 = self.rid("c")
        make_release(self.root, r1, git_ts=1789000000)
        make_release(self.root, r2, git_ts=1789000100)
        ps = [subprocess.Popen(
            ["bash", str(ACTIVATE), "activate", rid],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env_base)
            for rid in (r1, r2)]
        for p in ps:
            p.wait(timeout=180)
        self.assertEqual(self.current(), r2)


class TestT05FailureKeepsCurrent(ActivateFixture):
    """复验 P1b：五种失败注入，各断言旧可用 + 同 RID 可重试。"""

    def _setup_current(self):
        good = self.rid("a")
        make_release(self.root, good, git_ts=1789000000)
        self.activate("activate", good)
        return good

    def _assert_old_alive(self, old_rid):
        self.assertEqual(self.current(), old_rid)
        inc = self.effective_inc()
        self.assertIn(f"root {self.root}/releases/{old_rid}/site", inc)

    def _retry_same_rid(self, bad_rid):
        r = self.activate("activate", bad_rid, expect_rc=0)
        self.assertIn("activated", r.stdout)

    def test_fail_candidate_start(self):
        """失败注入 1：候选服务起不来（同 RID 重试场景重建）。"""
        old = self._setup_current()
        bad = self.rid("c")
        make_release(self.root, bad, git_ts=1789000200)
        (self.root / "shared" / "activate-hook").write_text("#!/bin/bash\nexit 1\n")
        (self.root / "shared" / "activate-hook").chmod(0o755)
        self.activate("activate", bad, expect_rc=5)
        # 重建场景后同 RID 成功
        self.tearDown()
        self.setUp()
        old2 = self.rid("a")
        make_release(self.root, old2, git_ts=1789000000)
        self.activate("activate", old2)
        make_release(self.root, bad, git_ts=1789000200)
        self.activate("activate", bad, expect_rc=0)

    def test_fail_nginx_test(self):
        """失败注入 2：nginx -t 失败。"""
        old = self._setup_current()
        bad = self.rid("c")
        make_release(self.root, bad, git_ts=1789000200)
        (self.root / "shared" / "state" / "FAIL_nginx_test").write_text("1")
        self.activate("activate", bad, expect_rc=7)
        self._assert_old_alive(old)
        (self.root / "shared" / "state" / "FAIL_nginx_test").unlink()
        self._retry_same_rid(bad)

    def test_fail_nginx_reload(self):
        """失败注入 3：nginx reload 失败。"""
        old = self._setup_current()
        bad = self.rid("c")
        make_release(self.root, bad, git_ts=1789000200)
        (self.root / "shared" / "state" / "FAIL_nginx_reload").write_text("1")
        self.activate("activate", bad, expect_rc=7)
        self._assert_old_alive(old)
        (self.root / "shared" / "state" / "FAIL_nginx_reload").unlink()
        self._retry_same_rid(bad)

    def test_fail_entry_smoke(self):
        """失败注入 4：切换后入口冒烟失败（SMOKE_URL 指向不存在的端口）。"""
        old = self._setup_current()
        bad = self.rid("c")
        make_release(self.root, bad, git_ts=1789000200)
        r = self.activate("activate", bad, expect_rc=7,
                          smoke_url=f"http://127.0.0.1:{self.smoke_port}/")
        self._assert_old_alive(old)
        self.assertIn("已恢复", r.stderr)
        self._retry_same_rid(bad)

    def test_fail_candidate_smoke(self):
        """失败注入 5：候选 status 冒烟失败（服务起在错误端口）。"""
        old = self._setup_current()
        bad = self.rid("c")
        make_release(self.root, bad, git_ts=1789000200)
        hook = self.root / "shared" / "activate-hook"
        hook.write_text("""#!/bin/bash
ACTION="$1"; SLOT="$2"; RID="$3"; PORT="${4:-0}"
if [ "$ACTION" = "start" ]; then
  python3 -c "
import http.server, threading, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Length','2'); self.end_headers(); self.wfile.write(b'{}')
    def log_message(self, *a): pass
srv = http.server.HTTPServer(('127.0.0.1', int(sys.argv[1]) + 1), H)
import time
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(60)
" "$PORT" >/dev/null 2>&1 &
fi
exit 0
""")
        hook.chmod(0o755)
        self.activate("activate", bad, expect_rc=5)
        # 重建后同 RID 成功
        self.tearDown()
        self.setUp()
        old2 = self.rid("a")
        make_release(self.root, old2, git_ts=1789000000)
        self.activate("activate", old2)
        make_release(self.root, bad, git_ts=1789000200)
        self.activate("activate", bad, expect_rc=0)


class TestT06TwoVersions(ActivateFixture):

    def test_current_and_previous_queryable(self):
        v1 = self.rid("a")
        v2 = self.rid("c")
        make_release(self.root, v1, git_ts=1789000000, ds="ds_" + "1" * 64)
        self.activate("activate", v1)
        d2 = make_release(self.root, v2, git_ts=1789000100, ds="ds_" + "2" * 64)
        m = json.loads((d2 / "data" / "manifest.json").read_text())
        m["retainedVersions"].append(
            {"datasetVersion": "ds_" + "1" * 64, "generatedAt": "x"})
        (d2 / "data" / "manifest.json").write_text(json.dumps(m))
        mm = rm.build_manifest(
            d2, rid=v2, git_commit="c" * 40, git_ts=1789000100,
            dataset_version="ds_" + "2" * 64, data_through="2026-09-17",
            built_at="2026-09-17T01:00:00Z")
        (d2 / "metadata" / "release-manifest.json").write_text(json.dumps(mm))
        self.activate("activate", v2)
        self.assertEqual(self.current(), v2)
        self.assertEqual(
            Path((self.root / "previous").resolve()).name, v1)


class TestP1aTripleSwitch(ActivateFixture):
    """复验 P1a：连续三激活 A→blue、B→green、C→blue。"""

    def test_blue_green_blue(self):
        a, b, c = self.rid("a"), self.rid("c"), self.rid("e")
        make_release(self.root, a, git_ts=1789000000)
        make_release(self.root, b, git_ts=1789000100)
        make_release(self.root, c, git_ts=1789000200)
        # A → blue
        self.activate("activate", a)
        slots = json.loads((self.root / "shared" / "state" / "slots.json").read_text())
        self.assertEqual(slots["rid_to_slot"][a], "blue")
        self.assertEqual(slots["slot_to_rid"]["blue"], a)
        inc = self.effective_inc()
        self.assertIn(f"root {self.root}/releases/{a}/site", inc)
        self.assertIn("127.0.0.1:8788", inc)  # blue 端口
        # B → green
        self.activate("activate", b)
        slots = json.loads((self.root / "shared" / "state" / "slots.json").read_text())
        self.assertEqual(slots["rid_to_slot"][b], "green")
        self.assertEqual(slots["slot_to_rid"]["green"], b)
        inc = self.effective_inc()
        self.assertIn(f"root {self.root}/releases/{b}/site", inc)
        self.assertIn("127.0.0.1:8789", inc)  # green 端口
        # C → blue（A 的旧映射被清理）
        self.activate("activate", c)
        slots = json.loads((self.root / "shared" / "state" / "slots.json").read_text())
        self.assertEqual(slots["rid_to_slot"][c], "blue")
        self.assertEqual(slots["slot_to_rid"]["blue"], c)
        self.assertNotIn(a, slots["rid_to_slot"])
        inc = self.effective_inc()
        self.assertIn(f"root {self.root}/releases/{c}/site", inc)
        self.assertIn("127.0.0.1:8788", inc)
        # 停槽调用记录
        hook_log = (self.root / "shared" / "state" / "hook.log").read_text()
        self.assertRegex(hook_log, r"stop blue")
        self.assertRegex(hook_log, r"stop green")


class TestT15Rollback(ActivateFixture):

    def test_rollback_with_reason(self):
        v1 = self.rid("a")
        v2 = self.rid("c")
        make_release(self.root, v1, git_ts=1789000000, ds="ds_" + "1" * 64)
        make_release(self.root, v2, git_ts=1789000100, ds="ds_" + "1" * 64)
        self.activate("activate", v1)
        self.activate("activate", v2)
        r = self.activate("rollback", v1, "--reason", "smoke-failed", expect_rc=0)
        self.assertIn("rolled back", r.stdout)
        self.assertEqual(self.current(), v1)
        log = (self.root / "shared" / "state" / "activations.log").read_text()
        self.assertIn("rollback", log)
        self.assertIn("smoke-failed", log)
        inc = self.effective_inc()
        self.assertIn(f"root {self.root}/releases/{v1}/site", inc)

    def test_rollback_requires_reason(self):
        v1 = self.rid("a")
        make_release(self.root, v1, git_ts=1789000000)
        r = self.activate("rollback", v1, expect_rc=2)
        self.assertIn("reason", r.stderr)

    def test_rollback_incompatible_ds_rejected(self):
        v1 = self.rid("a")
        v2 = self.rid("c")
        make_release(self.root, v1, git_ts=1789000000, ds="ds_" + "1" * 64)
        make_release(self.root, v2, git_ts=1789000100, ds="ds_" + "2" * 64)
        self.activate("activate", v1)
        self.activate("activate", v2)
        r = self.activate("rollback", v1, "--reason", "test", expect_rc=4)
        self.assertIn("不覆盖", r.stderr)


class TestStatusAction(ActivateFixture):

    def test_status_reports(self):
        rid = self.rid("a")
        make_release(self.root, rid, git_ts=1789000000)
        self.activate("activate", rid)
        r = self.activate("status", expect_rc=0)
        self.assertIn(rid, r.stdout)
        self.assertIn("current", r.stdout)
        self.assertIn("slots", r.stdout)

    def test_status_metadata_readonly(self):
        """M7：status 返回只读 metadata（datasetVersion/dataThrough/gitCommit）——
        verify-release.sh 经此取值，不再开放任意 python3 -c。"""
        rid = self.rid("a")
        ds = "ds_" + ("ab12" * 16)
        make_release(self.root, rid, git_ts=1789000000, ds=ds)
        self.activate("activate", rid)
        r = self.activate("status", expect_rc=0)
        self.assertIn(f"datasetVersion: {ds}", r.stdout)
        self.assertIn("dataThrough:    2026-09-16", r.stdout)
        self.assertIn("gitCommit:", r.stdout)


class TestSkipTestsMarked(ActivateFixture):
    """复验 P1c：testsSkipped=true 的 release 拒绝激活。"""

    def test_skipped_tests_release_rejected(self):
        rid = self.rid("a")
        make_release(self.root, rid, git_ts=1789000000)
        mp = self.root / "incoming" / rid / "metadata" / "release-manifest.json"
        m = json.loads(mp.read_text())
        m["testsSkipped"] = True
        mp.write_text(json.dumps(m))
        r = self.activate("activate", rid, expect_rc=6)
        self.assertIn("校验失败", r.stderr)  # testsSkipped 在 verify 错误清单中
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "v", str(BASE / "ops/server/release_manifest_verify.py"))
        v = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(v)
        errs = v.verify(self.root / "incoming" / rid)
        self.assertTrue(any("testsSkipped" in e and "禁止激活" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
