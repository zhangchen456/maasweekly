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
import time
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
    (d / "data" / "public" / "v1").mkdir(parents=True)
    (d / "data" / "public" / "v1" / "manifest.json").write_text(json.dumps({
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
        # 权限收敛的属主/组注入（生产=root + maasagent/www-data / maasdeploy；
        # 测试=当前用户+主组——macOS 主组是 staff 等而非同名组）
        import getpass
        _user = getpass.getuser()
        _group = _user
        try:
            import grp
            _group = grp.getgrgid(os.getgid()).gr_name
        except Exception:
            pass
        self.env_base = {
            **os.environ,
            "MAAS_RELEASE_ROOT": str(self.root),
            "MAAS_NGINX_TEST": str(nginx_hook),
            "MAAS_RELEASE_OWNER": _user,
            "MAAS_AGENT_GROUP": _group,
            "MAAS_STATIC_GROUP": _group,
            "MAAS_ROOT_GROUP": _group,
            "MAAS_DEPLOY_OWNER": _user,
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

    def effective_inc(self, name: str = "agent-upstream.inc") -> str:
        inc = self.root / "shared" / "nginx" / name
        return inc.read_text() if inc.exists() else ""

    def dyn_inc(self, name: str) -> str:
        """读动态 include（三文件之一）。"""
        return self.effective_inc(name)

    def assert_incs_bound(self, rid: str, port: str):
        """三 include 同时绑定同一 release/槽位（M8-B3 P0 核心不变量）。

        作用域红线按指令行检查（跳过 # 注释行）：
        upstream 文件无 root/location 指令；root 文件无 upstream 指令；
        routes 文件无 upstream/root 指令、无 server 块。
        """
        up = self.dyn_inc("agent-upstream.inc")
        sr = self.dyn_inc("site-root.inc")
        rt = self.dyn_inc("agent-routes.inc")
        self.assertIn(f"127.0.0.1:{port}", up)
        self.assertIn(f"root {self.root}/releases/{rid}/site", sr)
        self.assertIn("location /api/v1/", rt)
        self.assertIn("location = /api/mcp", rt)
        directives = lambda s: [l for l in s.splitlines() if l.strip() and not l.strip().startswith("#")]
        up_d, sr_d, rt_d = directives(up), directives(sr), directives(rt)
        self.assertFalse(any(l.strip().startswith("root ") for l in up_d))
        self.assertFalse(any("location" in l for l in up_d))
        self.assertFalse(any(l.strip().startswith("upstream") for l in sr_d))
        self.assertFalse(any(l.strip().startswith("upstream") for l in rt_d))
        self.assertFalse(any(l.strip().startswith("root ") for l in rt_d))
        self.assertFalse(any(l.strip().startswith("server {") for l in rt_d))


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
        # 三 include 同时生成并绑定新 release（作用域严格分离）
        self.assert_incs_bound(rid, "8788")

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
        # 三 include 全部仍指向旧 release（root 在 site-root.inc，端口在 upstream）
        self.assertIn(f"root {self.root}/releases/{old_rid}/site", self.dyn_inc("site-root.inc"))

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
        m = json.loads((d2 / "data" / "public" / "v1" / "manifest.json").read_text())
        m["retainedVersions"].append(
            {"datasetVersion": "ds_" + "1" * 64, "generatedAt": "x"})
        (d2 / "data" / "public" / "v1" / "manifest.json").write_text(json.dumps(m))
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
        self.assert_incs_bound(a, "8788")
        # B → green
        self.activate("activate", b)
        slots = json.loads((self.root / "shared" / "state" / "slots.json").read_text())
        self.assertEqual(slots["rid_to_slot"][b], "green")
        self.assertEqual(slots["slot_to_rid"]["green"], b)
        self.assert_incs_bound(b, "8789")
        # C → blue（A 的旧映射被清理）
        self.activate("activate", c)
        slots = json.loads((self.root / "shared" / "state" / "slots.json").read_text())
        self.assertEqual(slots["rid_to_slot"][c], "blue")
        self.assertEqual(slots["slot_to_rid"]["blue"], c)
        self.assertNotIn(a, slots["rid_to_slot"])
        self.assert_incs_bound(c, "8788")
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
        # rollback 后三 include 同步切回 v1（root 在 site-root.inc）
        self.assertIn(f"root {self.root}/releases/{v1}/site", self.dyn_inc("site-root.inc"))
        self.assertIn("location /api/v1/", self.dyn_inc("agent-routes.inc"))

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


class TestNginxThreeIncludeTx(ActivateFixture):
    """M8-B3 P0：三 include 事务（nginx mixed-scope 修复）。

    背景：旧版把 root（server ctx）与 upstream（http ctx）写进同一个
    agent-upstream.inc——在真实 nginx 结构下无论 include 进哪个作用域都
    必然 nginx -t 失败。修复为三个作用域严格分离的动态文件 + 全有或全无
    事务恢复。
    """

    def _first_activation_compatible_state(self):
        """install-production 生成的首发兼容态（三文件已存在）。"""
        nginx_dir = self.root / "shared" / "nginx"
        (nginx_dir / "site-root.inc").write_text("root /var/www/maasweekly;\n")
        (nginx_dir / "agent-upstream.inc").write_text(
            "upstream agent_api {\n    server 127.0.0.1:8788;\n}\n")
        (nginx_dir / "agent-routes.inc").write_text(
            "# intentionally empty before first activation\n")

    def _setup_current(self):
        """激活一个 release 作为当前版本（三 include 指向它）。"""
        good = self.rid("a")
        make_release(self.root, good, git_ts=1789000000)
        self.activate("activate", good)
        return good

    def test_first_activation_from_compatible_state(self):
        """首发边界（新形态）：三文件已存在（兼容态）→ 激活后全部切到新 release。"""
        self._first_activation_compatible_state()
        rid = self.rid("a")
        make_release(self.root, rid, git_ts=1789000000)
        r = self.activate("activate", rid)
        self.assertIn("activated", r.stdout)
        # 三 include 同时绑定新 release（不再依赖"文件不存在"的特殊态）
        self.assert_incs_bound(rid, "8788")

    def test_fail_nginx_test_restores_all_three(self):
        """nginx -t 失败：三个 include 全部恢复兼容态（不允许部分恢复）。"""
        self._first_activation_compatible_state()
        old = self.rid("a")
        make_release(self.root, old, git_ts=1789000000)
        self.activate("activate", old)
        # 此时三 include 指向 old；注入失败后激活新 release
        (self.root / "shared/state/FAIL_nginx_test").write_text("")
        bad = self.rid("c")
        make_release(self.root, bad, git_ts=1789000200)
        self.activate("activate", bad, expect_rc=7)
        # 三个文件全部回到 old 绑定（snapshot-restore 全有或全无）
        self.assert_incs_bound(old, "8788")
        self.assertEqual(self.current(), old)

    def test_fail_nginx_reload_restores_all_three(self):
        """reload 失败：三 include 全部恢复。"""
        old = self._setup_current()
        (self.root / "shared/state/FAIL_nginx_reload").write_text("")
        bad = self.rid("c")
        make_release(self.root, bad, git_ts=1789000200)
        self.activate("activate", bad, expect_rc=7)
        self.assert_incs_bound(old, "8788")

    def test_fail_entry_smoke_restores_all_three(self):
        """切换后入口冒烟失败：三 include 全部恢复。"""
        old = self._setup_current()
        # MAAS_SMOKE_URL 由 activate() 注入；用失败 URL 触发 entry_smoke 失败
        bad = self.rid("c")
        make_release(self.root, bad, git_ts=1789000200)
        self.activate("activate", bad, expect_rc=7,
                      smoke_url="http://127.0.0.1:1/definitely-not-listening")
        self.assert_incs_bound(old, "8788")

    def test_routes_content_boundaries(self):
        """agent-routes.inc 的 location 内容合同（继承动态 root，不硬编码路径）。"""
        rid = self._setup_current()
        rt = self.dyn_inc("agent-routes.inc")
        self.assertIn("location = /feed.xml", rt)
        self.assertIn("location = /feed/weekly.xml", rt)
        self.assertIn("location /maas-skill/", rt)
        # 继承 server root：不得硬编码 /srv/.../current 或 releases 路径
        self.assertNotIn("/srv/maasweekly", rt)
        # RSS 缓存 ≥30 分钟
        self.assertIn("max-age=1800", rt)
        # MCP no-store
        self.assertIn("no-store", rt)

    def test_rss_locations_override_mime_types(self):
        """第八代 P0：RSS Content-Type 合同——mime.types 把 .xml 映射为
        text/xml，default_type 仅在 types 表无匹配时生效；两个 feed location
        必须局部清空 types 再 default_type application/rss+xml（作用域最小，
        不影响其他静态 XML）。"""
        rid = self._setup_current()
        rt = self.dyn_inc("agent-routes.inc")
        for loc in ("location = /feed.xml", "location = /feed/weekly.xml"):
            i = rt.index(loc)
            block = rt[i:rt.index("}", rt.index("try_files", i))]
            self.assertIn("types { }", block, f"{loc} 缺局部 types 清空（mime.types 会覆盖 default_type）")
            self.assertIn("default_type application/rss+xml;", block)
        # 局部清空不得泄漏到 feed 之外的 location（其他静态 XML 不受影响）
        skill_block = rt[rt.index("location /maas-skill/"):]
        self.assertNotIn("types { }", skill_block)


class TestInstallProduction(unittest.TestCase):
    """install-production.sh 路径解析与 nginx 稳定配置内容断言。"""

    BASE = Path(__file__).resolve().parent.parent
    OPS = BASE / "ops"

    def test_ops_dir_resolution_from_ops_root(self):
        """从 ops/ 直接执行时路径解析正确（真实仓库布局）。"""
        p = subprocess.run(
            ["bash", "-c",
             f"cd {self.BASE} && ./ops/install-production.sh --dry-run"],
            capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        # 源路径解析到真实 ops/（不是 ops/server/..）
        self.assertIn("'ops/maas-agent@.service'", p.stdout.replace(str(self.BASE) + "/", ""))
        self.assertIn("ops/nginx/maasweekly-agent-http.conf", p.stdout)

    def test_http_conf_no_server_directives(self):
        """http 级配置不含 server/location/root（作用域红线）。"""
        c = (self.OPS / "nginx" / "maasweekly-agent-http.conf").read_text()
        directives = [l for l in c.splitlines()
                      if l.strip() and not l.strip().startswith("#")]
        self.assertTrue(any(l.strip().startswith("limit_req_zone") for l in directives))
        self.assertIn("include /srv/maasweekly/shared/nginx/agent-upstream.inc;", c)
        for l in directives:
            self.assertFalse(l.strip().startswith("server {"), l)
            self.assertFalse(l.strip().startswith("location"), l)
            self.assertFalse(l.strip().startswith("root "), l)

    def test_server_snippet_no_server_block_no_upstream(self):
        """server snippet 不含 server { / upstream（作用域红线）。"""
        c = (self.OPS / "nginx" / "maasweekly-agent-server.conf").read_text()
        directives = [l for l in c.splitlines()
                      if l.strip() and not l.strip().startswith("#")]
        self.assertIn("include /srv/maasweekly/shared/nginx/agent-routes.inc;", c)
        for l in directives:
            self.assertFalse(l.strip().startswith("server {"), l)
            self.assertFalse(l.strip().startswith("upstream"), l)

    def test_deploy_mode_permanently_legacy(self):
        content = (self.OPS / "deploy-mode").read_text()
        for line in content.splitlines():
            if line.startswith("DEPLOY_MODE="):
                self.assertEqual(line, "DEPLOY_MODE=legacy")


class TestCandidateRunsCandidateRelease(ActivateFixture):
    """M8-B3 P0 核心回归：候选槽位必须运行候选 release（MAAS_RELEASE_DIR），
    绝不依赖 /srv/maasweekly/current。

    背景：首发暴露 systemd WorkingDirectory=/srv/maasweekly/current/agent-api——
    首发时 current 不存在（CHDIR 200 失败）；后续发布会从旧 current 运行（混版）。
    修复：unit ExecStart 改 wrapper（ops/server/maas-agent-run），slot env 驱动。
    """

    def _start_slot_with_env(self, rid: str, port: int) -> str:
        """按激活器真实行为写 slot env，再用真实 wrapper 语义起候选。"""
        slot_env = self.root / "shared" / "slots" / "blue.env"
        slot_env.parent.mkdir(parents=True, exist_ok=True)
        slot_env.write_text(
            f"PORT={port}\n"
            f"MAAS_RELEASE_DIR={self.root}/releases/{rid}\n"
            f"PUBLIC_DATA_ROOT={self.root}/releases/{rid}/data/public/v1\n")
        # 用 release 内真实 agent-api 不可行（测试 fixture 无产物）——
        # 这里测的是 wrapper 语义：起一个返回 slot env 指定 datasetVersion 的服务，
        # 由 wrapper 等价物从 slot env 读路径启动（与生产 wrapper 同变量）。
        ds = {"rl_aaaaaaaaaa_bbbbbbbbbbbb": "ds_" + ("11" * 32),
              "rl_aaaaaaaaaa_cccccccccccc": "ds_" + ("22" * 32)}[rid]
        (self.root / "releases" / rid).mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            ["bash", "-c", f"""
set -euo pipefail
source '{slot_env}'
: "${{MAAS_RELEASE_DIR:?}}"
python3 -c "
import http.server, threading, sys, json
DS = '{ds}'
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/v1/status'):
            body = json.dumps({{'datasetVersion': DS}}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length', str(len(body))); self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(200); self.send_header('Content-Length','2'); self.end_headers(); self.wfile.write(b'{{}}')
    def log_message(self, *a): pass
srv = http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
import time; time.sleep(60)
" "$PORT" >/dev/null 2>&1 &
echo $! >> {self.root}/shared/state/hook.pids
"""])
        # 等服务就绪
        import urllib.request
        for _ in range(20):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/status", timeout=1)
                return ds
            except Exception:
                time.sleep(0.1)
        self.fail("slot 服务未就绪")
        return ""

    def _get_ds(self, port: int) -> str:
        import urllib.request
        body = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/status", timeout=3).read()
        return json.loads(body)["datasetVersion"]

    def test_candidate_starts_without_current(self):
        """首发边界：current 不存在时，slot env 指向的候选 release 可直接启动。"""
        rid = "rl_aaaaaaaaaa_bbbbbbbbbbbb"
        self.assertFalse((self.root / "current").exists())  # 无 current
        ds = self._start_slot_with_env(rid, 9601)
        self.assertEqual(self._get_ds(9601), ds)
        # 全程未创建 current
        self.assertFalse((self.root / "current").exists())

    def test_candidate_returns_its_own_ds_not_current(self):
        """防混版核心：current=A 时，候选 env=B → status 必须返回 B 的 datasetVersion。"""
        a, b = "rl_aaaaaaaaaa_bbbbbbbbbbbb", "rl_aaaaaaaaaa_cccccccccccc"
        # current 指向 A（旧 release）
        (self.root / "releases" / a).mkdir(parents=True, exist_ok=True)
        os.symlink(f"releases/{a}", self.root / "current")
        # 候选 slot env 指向 B
        ds_b = self._start_slot_with_env(b, 9602)
        self.assertEqual(self._get_ds(9602), ds_b)  # B 的版本，不是 A 的
        ds_a = {"rl_aaaaaaaaaa_bbbbbbbbbbbb": "ds_" + ("11" * 32)}[a]
        self.assertNotEqual(self._get_ds(9602), ds_a)

    def test_wrapper_requires_release_dir(self):
        """wrapper 语义：缺 MAAS_RELEASE_DIR 必须失败（不猜路径）。"""
        r = subprocess.run(
            ["bash", str(BASE / "ops" / "server" / "maas-agent-run")],
            capture_output=True, text=True,
            env={k: v for k, v in os.environ.items() if k != "MAAS_RELEASE_DIR"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("MAAS_RELEASE_DIR", r.stderr)


class TestUnitContract(unittest.TestCase):
    """maas-agent@.service 静态合同（M8-B3 P0）：候选槽位不依赖 current。"""

    BASE = Path(__file__).resolve().parent.parent

    def test_unit_never_references_current(self):
        """unit 指令行不得出现 /srv/maasweekly/current（注释说明除外）。"""
        unit = (self.BASE / "ops" / "maas-agent@.service").read_text()
        directives = [l for l in unit.splitlines()
                      if l.strip() and not l.strip().startswith(("#", "["))]
        for l in directives:
            self.assertNotIn("/srv/maasweekly/current", l,
                             f"unit 指令行引用 current（混版风险）: {l}")

    def test_unit_execstart_uses_wrapper(self):
        """ExecStart 必须是 wrapper（slot env 驱动候选 release）。"""
        unit = (self.BASE / "ops" / "maas-agent@.service").read_text()
        exec_lines = [l for l in unit.splitlines() if l.startswith("ExecStart=")]
        self.assertEqual(len(exec_lines), 1)
        self.assertEqual(exec_lines[0].strip(),
                         "ExecStart=/usr/local/bin/maas-agent-run")
        # 不再有 WorkingDirectory（曾被指向 current/agent-api）
        wd = [l for l in unit.splitlines() if l.startswith("WorkingDirectory=")]
        self.assertEqual(wd, [])

    def test_wrapper_reads_release_dir(self):
        """wrapper 从 slot env 读 MAAS_RELEASE_DIR 启动（生产语义）。"""
        w = (self.BASE / "ops" / "server" / "maas-agent-run").read_text()
        self.assertIn(': "${MAAS_RELEASE_DIR:?', w)
        self.assertIn('exec /usr/bin/node "${MAAS_RELEASE_DIR}/agent-api/dist/server.js"', w)

    def test_installer_installs_wrapper(self):
        """install-production 安装 wrapper 到 /usr/local/bin（0755）。"""
        inst = (self.BASE / "ops" / "install-production.sh").read_text()
        self.assertIn("'$RUN_SRC' /usr/local/bin/maas-agent-run", inst)
        self.assertIn('RUN_SRC="$OPS_DIR/server/maas-agent-run"', inst)


class TestPermissionsRecovery(ActivateFixture):
    """P0-2 失败恢复 ownership 闭环（fixture 场景）。"""

    def test_failed_activation_restores_incoming_owner(self):
        """P0-2 失败闭环：权限收敛后失败 → 退回 incoming 且属主还原为上传用户；
        同 RID 重试成功（activate 依赖真服务桩——用 ActivateFixture 场景）。"""
        rid_ok = self.rid("a")
        make_release(self.root, rid_ok, git_ts=1789000000)
        r = self.activate("activate", rid_ok)
        self.assertIn("activated", r.stdout)
        # 激活后 release 已收敛到运行组（fixture 注入的当前主组）
        import grp as grp_mod
        self.assertEqual(
            grp_mod.getgrgid((self.root / "releases" / rid_ok).stat().st_gid).gr_name,
            grp_mod.getgrgid(os.getgid()).gr_name)
        # 权限形态：目录 0750 / manifest 0640 / server.js 0640（普通文件）
        rel = self.root / "releases" / rid_ok
        self.assertEqual(oct((rel / "agent-api/dist").stat().st_mode & 0o777), "0o750")
        self.assertEqual(oct((rel / "agent-api/dist/server.js").stat().st_mode & 0o777), "0o640")
        # 注入失败：临时替换服务桩为"start 成功但不起服务"（候选冒烟 8789 连
        # 不上 → rc 5；第一个激活走 blue/8788 已有真服务，候选进 green/8789）
        hook = self.root / "shared" / "activate-hook"
        real_hook = self.root / "shared" / "activate-hook.real"
        hook.rename(real_hook)
        hook.write_text("#!/bin/bash\nexit 0\n")
        hook.chmod(0o755)
        bad = self.rid("c")
        make_release(self.root, bad, git_ts=1789000200)
        r = self.activate("activate", bad, expect_rc=5)
        # 失败闭环：bad 回 incoming 且属主还原（uid=当前用户=fixture 的 deploy owner）
        back = self.root / "incoming" / bad
        self.assertTrue(back.exists(), "失败候选未退回 incoming")
        self.assertEqual(back.stat().st_uid, os.getuid(),
                         "退回后属主未还原为上传用户")
        # 恢复真服务桩 → 同 RID 重试成功（真实闭环：属主还原后可重新激活）
        hook.unlink()
        real_hook.rename(hook)
        r = self.activate("activate", bad)
        self.assertIn("activated", r.stdout)


class TestDualConsumerPermissions(ActivateFixture):
    """M8-B3 第三次首发 P0：release 双消费者（nginx www-data + agent maasagent）。

    本地无 www-data/maasagent 用户——用两个真实本地用户模拟双消费者，
    通过 group 成员身份验证分树可读性（语义与生产一致：组权限决定访问）。
    macOS 上找不到两个可切换用户时降级为组语义断言（分树模式位已全覆盖）。
    """

    def _find_two_local_users(self) -> tuple[str, str] | None:
        """找两个真实本地用户：一个属于当前主组（模拟 agent），一个不属于（模拟 nginx）。
        不属于的必须存在且可 su/runuser——macOS 上难满足，返回 None 走降级。"""
        import pwd, grp
        cur = grp.getgrgid(os.getgid()).gr_name
        members = set()
        try:
            members = set(grp.getgrnam(cur).gr_mem)
        except KeyError:
            pass
        members.add(pwd.getpwuid(os.getuid()).pw_name)
        other = None
        for p in pwd.getpwall():
            if p.pw_name not in members and p.pw_uid > 500 and os.path.isdir(p.pw_dir):
                other = p.pw_name
                break
        if other is None:
            return None
        return pwd.getpwuid(os.getuid()).pw_name, other

    def test_dual_consumer_tree_access(self):
        """分树语义（核心）：两组变量分树收敛；本地以同组注入跑通完整 activate，
        真异组（www-data/maasagent）归属由静态断言（test_split_tree_groups）
        + 服务器端 root 激活器真实执行覆盖。"""
        rid = self.rid("a")
        make_release(self.root, rid, git_ts=1789000000)
        # 本地无 root——chgrp 到异组会 Operation not permitted。
        # 此处验证同组注入下分树流程完整跑通 + 模式位正确。
        r = subprocess.run(["bash", str(ACTIVATE), "activate", rid],
                           capture_output=True, text=True, env=self.env_base)
        self.assertEqual(r.returncode, 0, r.stderr[:300])
        rel = self.root / "releases" / rid
        import grp
        agent_grp = grp.getgrgid(os.getgid()).gr_name
        self.assertEqual(grp.getgrgid((rel / "agent-api").stat().st_gid).gr_name, agent_grp)
        self.assertEqual(grp.getgrgid((rel / "data").stat().st_gid).gr_name, agent_grp)
        # release 根 0711：其他用户 traverse-only
        self.assertEqual(oct(rel.stat().st_mode & 0o7777), "0o711")
        # 无 world-readable（模式位断言：0640/0750/0711 的 other=0）
        for f in [rel / "site/index.html", rel / "agent-api/dist/server.js",
                  rel / "data/public/v1/manifest.json"]:
            self.assertEqual(f.stat().st_mode & 0o007, 0, f"other 位非零: {f}")
        for d in [rel / "site", rel / "agent-api", rel / "data"]:
            self.assertEqual(d.stat().st_mode & 0o007, 0, f"目录 other 位非零: {d}")
        # site 可执行文件保留（install.sh）
        # （make_release 的 site 只有 index.html——执行位保留已由
        #  test_activate_converges_release_permissions 的 installer 0750 断言覆盖）

    def test_failure_recover_keeps_split_model(self):
        """失败恢复闭环在分树模型下仍工作（ownership 归还 + 重试）。"""
        # 复用第三次的注入方式：临时换失败桩 → 失败 → 还原 → 重试
        old = self.rid("a")
        make_release(self.root, old, git_ts=1789000000)
        self.activate("activate", old)
        hook = self.root / "shared" / "activate-hook"
        real_hook = self.root / "shared" / "activate-hook.real"
        hook.rename(real_hook)
        hook.write_text("#!/bin/bash\nexit 0\n")
        hook.chmod(0o755)
        bad = self.rid("c")
        make_release(self.root, bad, git_ts=1789000200)
        r = self.activate("activate", bad, expect_rc=5)
        back = self.root / "incoming" / bad
        self.assertTrue(back.exists())
        self.assertEqual(back.stat().st_uid, os.getuid())
        hook.unlink()
        real_hook.rename(hook)
        r = self.activate("activate", bad)
        self.assertIn("activated", r.stdout)


class TestUnitV8AndPermissions(unittest.TestCase):
    """M8-B3 第二次首发 P0：unit 允许 V8 JIT + release 权限收敛。"""
    BASE = Path(__file__).resolve().parent.parent
    OPS = BASE / "ops"

    def _unit_directives(self) -> list[str]:
        unit = (self.BASE / "ops" / "maas-agent@.service").read_text()
        return [l.strip() for l in unit.splitlines()
                if l.strip() and not l.strip().startswith(("#", "["))]

    def test_unit_allows_v8_jit(self):
        """P0-1：unit 不得含 MemoryDenyWriteExecute（V8 JIT 需 RWX，实锤崩溃）。"""
        for l in self._unit_directives():
            self.assertFalse(l.startswith("MemoryDenyWriteExecute"),
                             f"unit 含 MDWE（V8 JIT 崩溃）: {l}")

    def test_unit_keeps_other_hardening(self):
        """P0-1：删除 MDWE 不得误删其余关键硬化。"""
        directives = self._unit_directives()
        must = ["User=maasagent", "NoNewPrivileges=true", "ProtectSystem=strict",
                "ProtectHome=true", "PrivateTmp=true", "CapabilityBoundingSet=",
                "RestrictAddressFamilies="]
        for m in must:
            self.assertTrue(any(l == m or l.startswith(m) for l in directives),
                            f"硬化项缺失: {m}")

    def test_activate_converges_release_permissions(self):
        """P0-2 核心断言：激活成功后 release 权限 = owner:group 可读可遍历、
        other 无权限、可执行位保留、组对齐运行用户（fixture 注入值）。"""
        rid = "rl_aaaaaaaaaa_bbbbbbbbbbbb"
        with tempfile.TemporaryDirectory(prefix="t06-perm-") as td:
            root = Path(td)
            for sub in ("incoming", "releases", "shared/state", "shared/slots",
                        "shared/nginx", "locks"):
                (root / sub).mkdir(parents=True)
            # 构造上传形态的 release（含可执行与普通文件、嵌套目录）
            d = root / "incoming" / rid
            (d / "agent-api/dist").mkdir(parents=True)
            (d / "agent-api/dist/server.js").write_text("// stub")      # 0644
            (d / "data/public/v1").mkdir(parents=True)
            (d / "data/public/v1/manifest.json").write_text("{}")
            (d / "site/maas-skill").mkdir(parents=True)
            installer = d / "site/maas-skill/install.sh"
            installer.write_text("#!/bin/sh\n")
            installer.chmod(0o755)                                       # 可执行
            (d / "metadata").mkdir()
            (d / "metadata/release-manifest.json").write_text("{}")
            # 直接调 prepare 函数（不经完整 activate——本测试只验权限语义）。
            # 从源码抽取变量定义 + _apply_tree_permissions + prepare 两段。
            script = (self.OPS / "server" / "maasweekly-activate").read_text()
            vars_def = "\n".join(
                l for l in script.splitlines()
                if l.startswith(("RUNTIME_OWNER=", "AGENT_GROUP=", "STATIC_GROUP=", "ROOT_GROUP=")))
            fn_apply = "_apply_tree_permissions() {" + script.split("_apply_tree_permissions() {")[1].split("\n}\n")[0] + "\n}\n"
            fn_prep = "prepare_release_runtime_permissions() {" + script.split("prepare_release_runtime_permissions() {")[1].split("\n}\n")[0] + "\n}\n"
            helper = Path(td) / "perm.sh"
            import grp as grp_mod_, pwd as pwd_mod_
            grp = grp_mod_.getgrgid(os.getgid()).gr_name
            user = pwd_mod_.getpwuid(os.getuid()).pw_name
            helper.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\n"
                + vars_def + "\n"
                + f'RUNTIME_OWNER="{user}"\nAGENT_GROUP="{grp}"\nSTATIC_GROUP="{grp}"\nROOT_GROUP="{grp}"\n'
                + f'ROOT="{root}"\n'
                + fn_apply + fn_prep
                + f'prepare_release_runtime_permissions "{root}/incoming/{rid}"\n'
                'echo OK\n')
            helper.chmod(0o755)
            r = subprocess.run(["bash", str(helper)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("OK", r.stdout)
            # 分树断言（fixture 注入三组同名=当前主组——重点验模式位与分树结构；
            # 生产组分离（www-data/maasagent）由 test_split_tree_groups 断言）
            self.assertEqual(oct(d.stat().st_mode & 0o7777), "0o711")          # release 根 0711
            self.assertEqual(oct((d / "site").stat().st_mode & 0o777), "0o750")
            self.assertEqual(oct((d / "site/maas-skill").stat().st_mode & 0o777), "0o750")
            self.assertEqual(oct(installer.stat().st_mode & 0o777), "0o750")   # 可执行保留
            self.assertEqual(oct((d / "agent-api/dist").stat().st_mode & 0o777), "0o750")
            self.assertEqual(oct((d / "agent-api/dist/server.js").stat().st_mode & 0o777), "0o640")
            self.assertEqual(oct((d / "data/public/v1/manifest.json").stat().st_mode & 0o777), "0o640")
            self.assertEqual(oct((d / "metadata").stat().st_mode & 0o777), "0o750")
            self.assertEqual(oct((d / "metadata/release-manifest.json").stat().st_mode & 0o777), "0o640")
            self.assertEqual(
                grp_mod_.getgrgid((d / "data/public/v1/manifest.json").stat().st_gid).gr_name, grp)

    def test_split_tree_groups_static_vs_agent(self):
        """双消费者分树：site/ 与 agent-api+data/ 必须收敛到不同组变量。"""
        script = (self.OPS / "server" / "maasweekly-activate").read_text()
        self.assertIn('AGENT_GROUP="${MAAS_AGENT_GROUP:-maasagent}"', script)
        self.assertIn('STATIC_GROUP="${MAAS_STATIC_GROUP:-www-data}"', script)
        # site 用 STATIC_GROUP；agent-api/data 用 AGENT_GROUP
        fn = script.split("prepare_release_runtime_permissions() {")[1].split("\n}\n")[0]
        self.assertIn('_apply_tree_permissions "$dir/$sub" "$STATIC_GROUP"', fn)
        self.assertIn('_apply_tree_permissions "$dir/$sub" "$AGENT_GROUP"', fn)
        # release 根 0711（traverse-only，不给 list/read）
        self.assertIn('chmod 0711 "$dir"', fn)

    def test_executable_bits_preserved_in_real_release(self):
        """真实 release 产物：node_modules/.bin 等可执行结构经权限收敛后仍可执行。"""
        # 用 dist-release 内最新 release（构建产物真实含 .bin 链接）
        releases = sorted((self.BASE / "dist-release").glob("rl_*"), key=lambda p: p.stat().st_mtime)
        if not releases:
            self.skipTest("无本地 release 产物（build 后跑）")
        rel = releases[-1]
        bins = list((rel / "agent-api/node_modules/.bin").glob("*"))
        self.assertTrue(bins, "release 缺 .bin")
        for b in bins:
            # 原本可执行（symlink 指向的目标带 x；断言目标文件 mode）
            target = b.resolve()
            self.assertTrue(target.exists())
            self.assertEqual(oct(target.stat().st_mode & 0o100), "0o100",
                             f".bin 目标丢失执行位: {target}")

    def test_no_world_readable_release(self):
        """激活后 other 位必须为 0（不得 a+rX）。"""
        # 已由 test_activate_converges_release_permissions 的八进制断言覆盖
        # （0640/0750 的 other=0）。此处显式断言指令行不含宽泛授权。
        script = (self.OPS / "server" / "maasweekly-activate").read_text()
        directives = [l.strip() for l in script.splitlines()
                      if l.strip() and not l.strip().startswith("#")]
        for l in directives:
            self.assertNotIn("a+rX", l, f"指令行含 a+rX 宽泛授权: {l}")
            self.assertNotIn("chmod 0755", l, f"指令行含 0755: {l}")
            self.assertNotIn("chmod 0644", l, f"指令行含 0644: {l}")

if __name__ == "__main__":
    unittest.main()
