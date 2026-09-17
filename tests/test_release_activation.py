"""Task 06 激活协议测试（T04–T06、T15）。

ops/server/maasweekly-activate 以 MAAS_RELEASE_ROOT 注入临时目录；
蓝绿服务用 shared/activate-hook 桩模拟（生产为 systemd）。
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
    # 确定性合法 ds：rid 十六进制段映射到 64 hex（同 rid 同 ds）
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
    (d / "metadata").mkdir(exist_ok=True)
    (d / "metadata" / "release-manifest.json").write_text(json.dumps(m))
    return d


class ActivateFixture(unittest.TestCase):
    """临时 release root + activate-hook 桩（模拟蓝绿服务与冒烟）。"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="t06-act-"))
        for sub in ("incoming", "releases", "shared/state", "shared/slots",
                    "shared/nginx", "locks"):
            (self.root / sub).mkdir(parents=True)
        # activate-hook 桩：记录调用 + 模拟服务可答（冒烟 curl 不可达时
        # activate 会失败——桩里起一个真实微型 HTTP 服打 status）
        hook = self.root / "shared" / "activate-hook"
        hook.write_text(f"""#!/bin/bash
# 测试桩：start/stop 槽位——在传入的槽位端口上起模拟 status 服务
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
threading.Thread(target=srv.serve_forever, daemon=True).start()
import time; time.sleep(600)
" "$PORT" >/dev/null 2>&1 &
  echo $! >> {self.root}/shared/state/hook.pids
fi
exit 0
""")
        hook.chmod(0o755)

    def tearDown(self):
        # 清理桩进程
        pids = self.root / "shared" / "state" / "hook.pids"
        if pids.exists():
            for pid in pids.read_text().split():
                try:
                    os.kill(int(pid), 9)
                except (ProcessLookupError, ValueError):
                    pass
        shutil.rmtree(self.root, ignore_errors=True)

    def activate(self, *args, expect_rc=0):
        env = {**os.environ, "MAAS_RELEASE_ROOT": str(self.root)}
        r = subprocess.run(["bash", str(ACTIVATE), *args],
                           capture_output=True, env=env, timeout=120)
        r.stdout = r.stdout.decode("utf-8", errors="replace")
        r.stderr = r.stderr.decode("utf-8", errors="replace")
        if expect_rc is not None:
            self.assertEqual(r.returncode, expect_rc,
                             f"rc={r.returncode} stderr={r.stderr[:300]}")
        return r


class TestT04Basic(ActivateFixture):

    def test_first_activate(self):
        rid = "rl_" + "a" * 10 + "_" + "b" * 12
        make_release(self.root, rid, git_ts=1789000000)
        r = self.activate("activate", rid)
        self.assertIn("activated", r.stdout)
        self.assertEqual((self.root / "current").resolve(),
                         (self.root / "releases" / rid).resolve())
        self.assertFalse((self.root / "incoming" / rid).exists())

    def test_idempotent_same_release(self):
        rid = "rl_" + "a" * 10 + "_" + "b" * 12
        make_release(self.root, rid, git_ts=1789000000)
        self.activate("activate", rid)
        r = self.activate("activate", rid, expect_rc=0)
        self.assertIn("幂等", r.stdout)

    def test_stale_commit_rejected(self):
        old = "rl_" + "a" * 10 + "_" + "b" * 12
        new = "rl_" + "c" * 10 + "_" + "d" * 12
        make_release(self.root, old, git_ts=1789000100)
        make_release(self.root, new, git_ts=1789000000)  # 更旧
        self.activate("activate", old)
        r = self.activate("activate", new, expect_rc=4)
        self.assertIn("旧提交", r.stderr)

    def test_invalid_rid_rejected(self):
        r = self.activate("activate", "rl_$(evil)_x", expect_rc=2)
        self.assertIn("格式非法", r.stderr)

    def test_identity_conflict_rejected(self):
        rid = "rl_" + "a" * 10 + "_" + "b" * 12
        make_release(self.root, rid, git_ts=1789000000)
        self.activate("activate", rid)
        # 同 ID 不同内容重新上传（重算 manifest——内容变但 ID 同）
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
        r1 = "rl_" + "a" * 10 + "_" + "b" * 12
        r2 = "rl_" + "c" * 10 + "_" + "d" * 12
        make_release(self.root, r1, git_ts=1789000000)
        make_release(self.root, r2, git_ts=1789000100)
        env = {**os.environ, "MAAS_RELEASE_ROOT": str(self.root)}
        # 两个并发 activate（r2 更新——都应按序处理，最终 r2 生效）
        ps = [subprocess.Popen(["bash", str(ACTIVATE), "activate", rid],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=env)
              for rid in (r1, r2)]
        outs = [p.communicate() for p in ps]
        # 两个都成功（串行化后按时间序处理）或旧的被拒（如果 r2 先拿到锁）
        rcs = sorted(p.returncode for p in ps)
        self.assertIn(rcs[1], (0,))  # 至少最新成功
        cur = (self.root / "current").resolve().name
        self.assertEqual(cur, r2)


class TestT05FailureKeepsCurrent(ActivateFixture):

    def test_tampered_release_rejected_current_unchanged(self):
        good = "rl_" + "a" * 10 + "_" + "b" * 12
        make_release(self.root, good, git_ts=1789000000)
        self.activate("activate", good)
        before = (self.root / "current").resolve()
        bad = "rl_" + "c" * 10 + "_" + "d" * 12
        d = make_release(self.root, bad, git_ts=1789000200)
        (d / "site" / "index.html").write_text("TAMPERED")  # hash 不符
        r = self.activate("activate", bad, expect_rc=6)
        self.assertIn("校验失败", r.stderr)
        self.assertEqual((self.root / "current").resolve(), before)
        self.assertFalse((self.root / "releases" / bad).exists())  # 无半发布

    def test_missing_incoming_rejected(self):
        r = self.activate("activate", "rl_" + "e" * 10 + "_" + "f" * 12,
                          expect_rc=2)
        self.assertIn("incoming", r.stderr)

    def test_broken_candidate_service_current_unchanged(self):
        good = "rl_" + "a" * 10 + "_" + "b" * 12
        make_release(self.root, good, git_ts=1789000000)
        self.activate("activate", good)
        before = (self.root / "current").resolve()
        # 破坏 hook（start 失败 → 候选冒烟必败）
        (self.root / "shared" / "activate-hook").write_text("#!/bin/bash\nexit 1\n")
        (self.root / "shared" / "activate-hook").chmod(0o755)
        bad = "rl_" + "c" * 10 + "_" + "d" * 12
        make_release(self.root, bad, git_ts=1789000200)
        self.activate("activate", bad, expect_rc=5)
        self.assertEqual((self.root / "current").resolve(), before)


class TestT06TwoVersions(ActivateFixture):

    def test_current_and_previous_queryable(self):
        """激活后 current 生效；再激活新版（不同 datasetVersion）→ previous 保留。"""
        v1 = "rl_" + "a" * 10 + "_" + "b" * 12
        v2 = "rl_" + "c" * 10 + "_" + "d" * 12
        make_release(self.root, v1, git_ts=1789000000, ds="ds_" + "1" * 64)
        self.activate("activate", v1)
        # v2 的 data 保留 v1 的 ds（retainedVersions）
        d2 = make_release(self.root, v2, git_ts=1789000100, ds="ds_" + "2" * 64)
        m = json.loads((d2 / "data" / "manifest.json").read_text())
        m["retainedVersions"].append(
            {"datasetVersion": "ds_" + "1" * 64, "generatedAt": "x"})
        (d2 / "data" / "manifest.json").write_text(json.dumps(m))
        # 重算 manifest
        mm = rm.build_manifest(
            d2, rid=v2, git_commit="c" * 40, git_ts=1789000100,
            dataset_version="ds_" + "2" * 64, data_through="2026-09-17",
            built_at="2026-09-17T01:00:00Z")
        (d2 / "metadata" / "release-manifest.json").write_text(json.dumps(mm))
        self.activate("activate", v2)
        self.assertEqual((self.root / "current").resolve().name, v2)
        self.assertEqual((self.root / "previous").resolve().name, v1)


class TestT15Rollback(ActivateFixture):

    def test_rollback_with_reason(self):
        v1 = "rl_" + "a" * 10 + "_" + "b" * 12
        v2 = "rl_" + "c" * 10 + "_" + "d" * 12
        make_release(self.root, v1, git_ts=1789000000, ds="ds_" + "1" * 64)
        make_release(self.root, v2, git_ts=1789000100, ds="ds_" + "1" * 64)
        self.activate("activate", v1)
        self.activate("activate", v2)
        r = self.activate("rollback", v1, "--reason", "smoke-failed", expect_rc=0)
        self.assertIn("rolled back", r.stdout)
        self.assertEqual((self.root / "current").resolve().name, v1)
        log = (self.root / "shared" / "state" / "activations.log").read_text()
        self.assertIn("rollback", log)
        self.assertIn("smoke-failed", log)

    def test_rollback_requires_reason(self):
        v1 = "rl_" + "a" * 10 + "_" + "b" * 12
        make_release(self.root, v1, git_ts=1789000000)
        r = self.activate("rollback", v1, expect_rc=2)
        self.assertIn("reason", r.stderr)

    def test_rollback_incompatible_ds_rejected(self):
        v1 = "rl_" + "a" * 10 + "_" + "b" * 12
        v2 = "rl_" + "c" * 10 + "_" + "d" * 12
        make_release(self.root, v1, git_ts=1789000000, ds="ds_" + "1" * 64)
        # v2 不保留 v1 的 ds
        make_release(self.root, v2, git_ts=1789000100, ds="ds_" + "2" * 64)
        self.activate("activate", v1)  # v1 进 releases（rollback 目标必须存在）
        self.activate("activate", v2)
        r = self.activate("rollback", v1, "--reason", "test", expect_rc=4)
        self.assertIn("不覆盖", r.stderr)


class TestStatusAction(ActivateFixture):

    def test_status_reports(self):
        rid = "rl_" + "a" * 10 + "_" + "b" * 12
        make_release(self.root, rid, git_ts=1789000000)
        self.activate("activate", rid)
        r = self.activate("status", expect_rc=0)
        self.assertIn(rid, r.stdout)
        self.assertIn("current", r.stdout)


if __name__ == "__main__":
    unittest.main()
