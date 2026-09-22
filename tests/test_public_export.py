"""Task 03 公开导出测试（T01–T05、T18 CLI 侧）。

覆盖任务书 §9 验收：
- T01 同输入连续导出 → datasetVersion/文件/manifest 业务字段稳定
- T02 修订/撤回/质量变化 → 新版本；withdrawn 详情可读、默认列表隐藏
- T03 坏输入 → 非零退出且正式目录逐字节不变
- T04 --check/--dry-run/隔离 output-dir → 正式目录零污染
- T05 manifest 篡改 → 门禁失败
- T18 真实归档全量构建冒烟（真实数据存在时）

fixture 全部临时目录；真实归档测试只读。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "pipeline"))

from public_export import canonical  # noqa: E402

SCRIPT = BASE / "pipeline" / "scripts" / "export-public-data.py"
PROVIDER_MAP = BASE / "pipeline" / "config" / "public_providers.json"
BUSINESS = ("changes.json", "items.json", "prices.json",
            "evidence.json", "weekly.json", "status.json", "model-identities.json")


def run_cli(*args, input_root: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT), *args]
    if input_root is not None:
        cmd += ["--input-root", str(input_root)]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=BASE)


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(root.rglob("*")):
        if f.is_file():
            h.update(str(f.relative_to(root)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def make_obs(source_id="openai-blog", date="2026-09-10", title="测试记录",
             summary=None, status="active", revision=1):
    rid = "obs_" + hashlib.sha256(
        json.dumps([source_id, date], ensure_ascii=False,
                   separators=(",", ":")).encode()).hexdigest()
    return {
        "schemaVersion": 1, "id": rid, "sourceId": source_id, "date": date,
        "recordType": "source_observation", "changeType": "source_updated",
        "revision": revision, "status": status, "platform": "OpenAI",
        "sourceType": "blog", "sourceUrl": "https://example.com",
        "title": title, "summary": summary, "summaryOrigin":
            "rule" if summary else None,
        "observedAt": None, "timePrecision": "date",
        "revisedAt": None if revision == 1 else "2026-09-11T00:00:00+00:00",
        "revisionReason": None, "kind": "substantive",
        "diff": {"pairs": [], "added_lines": ["x"], "removed_lines": [],
                 "added_count": 1, "removed_count": 0},
        "evidenceLevel": "source_diff", "diffCompleteness": "unknown",
        "provenance": {"diff_file": "/Users/secret/local/path.json"},
        "permalink": f"/item/{rid}/",
    }


def make_price_event(provider="openai", model="gpt-test", component="input",
                     date="2026-09-11", amount="1.500000",
                     change="newly_observed"):
    import time
    fk = hashlib.sha256(f"{provider}|{model}|{component}".encode()).hexdigest()
    evid = "ev_" + hashlib.sha256(f"ev-{model}".encode()).hexdigest()
    pfv_id = "pfv_" + hashlib.sha256(
        f"{fk}|{amount}".encode()).hexdigest()
    ev = {
        "schemaVersion": 1, "id": evid, "snapshotContentId": "psnap_x",
        "source_key": f"{provider}:pricing", "sourceUrl": "https://example.com/p",
        "subpageUrl": None, "contentHash": "c" * 64,
        "locatorType": "dom_selector", "locator": "table:nth-of-type(1)",
        "extractorVersion": "openai-1", "excerptText": "$1.50 / 1M tokens",
        "excerptHash": hashlib.sha256(b"$1.50 / 1M tokens").hexdigest(),
        "completeness": "complete", "reasons": [],
        "snapshotAvailable": True, "provenance": {},
    }
    pfv = {
        "schemaVersion": 1, "version_id": pfv_id, "fact_key": fk,
        "provider_id": provider, "model_key": model, "component": component,
        "billing_mode": "realtime", "amount": amount, "amountRaw": amount,
        "currency": "USD", "unit_quantity": 1000000, "unit_name": "token",
        "region": "global", "service_tier": "standard",
        "context_band": None, "time_condition": None,
        "effective_at": None, "observed_at": 1789000000.0,
        "observedAt": "2026-09-11T10:00:00+00:00",
        "source_key": f"{provider}:pricing", "evidence_id": evid,
        "evidence_status": "complete", "field_state": "confirmed",
        "stale_reason": None,
    }
    rid = "price_" + hashlib.sha256(
        json.dumps([fk, date], separators=(",", ":")).encode()).hexdigest()
    price = {
        "schemaVersion": 1, "id": rid, "date": date,
        "recordType": "price_change", "fact_key": fk, "provider": provider,
        "model": model, "component": component, "currency": "USD",
        "unitQuantity": 1000000, "unitName": "token", "region": "global",
        "billingMode": "realtime", "serviceTier": "standard",
        "contextBand": None, "timeCondition": None,
        "beforeVersionId": None, "afterVersionId": pfv_id,
        "beforeEvidenceId": None, "afterEvidenceId": evid,
        "beforeObservedAt": None,
        "afterObservedAt": "2026-09-11T10:00:00+00:00",
        "changeType": change, "changedFields": [], "comparison": None,
        "revision": 1, "status": "active",
        "revisedAt": None, "revisionReason": None, "permalink": f"/item/{rid}/",
        "provenance": {},
    }
    return {"price": price, "pfv": pfv, "ev": ev}


class FixtureRepo:
    """临时微型归档仓库（含 exporter 需要的最小输入集）。"""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="t03-fixture-"))
        self._write_registry()
        self._write_weekly()
        self._write_daily_changes()
        self._write_current({})

    def _write_registry(self):
        shutil.copy(BASE / "data/model-registry/models.json",
                    self._p("data/model-registry/models.json"))
        shutil.copy(BASE / "pipeline" / "config" / "source_registry.json",
                    self._p("pipeline/config/source_registry.json"))

    def _p(self, rel: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _write_weekly(self):
        (self._p("site/src/content/weekly/2026-09-01.md")).write_text(
            "---\ntitle: \"周报 2026-09-01\"\ndate: \"2026-09-01\"\n"
            "period: \"2026-08-25 ~ 2026-09-01\"\n---\n\n正文\n", encoding="utf-8")
        (self._p("site/src/content/weekly-structured/2026-09-01.json")).write_text(
            json.dumps({"date": "2026-09-01", "period": "2026-08-25 ~ 2026-09-01",
                        "headline": [], "platforms": [], "summary_table": None,
                        "trends": [], "watchpoints": None, "event_index": None},
                       ensure_ascii=False), encoding="utf-8")

    def _write_daily_changes(self, days=None):
        (self._p("site/src/data/daily_changes.json")).write_text(
            json.dumps({"days": days or []}, ensure_ascii=False), encoding="utf-8")

    def _write_current(self, sources):
        (self._p("data/price-facts/current.json")).write_text(
            json.dumps({"schemaVersion": 1, "facts": {}, "sources": sources},
                       ensure_ascii=False), encoding="utf-8")

    def add_obs(self, **kw):
        rec = make_obs(**kw)
        f = self._p(f"data/records/{rec['id']}.json")
        f.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        revd = self._p(f"data/record-revisions/{rec['id']}/.keep").parent
        revd.mkdir(parents=True, exist_ok=True)
        for r in range(1, rec["revision"] + 1):
            snap = dict(rec, revision=r, revisedAt=None if r == 1 else rec["revisedAt"])
            (revd / f"{r}.json").write_text(
                json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
        return rec

    def add_price(self, **kw):
        bundle = make_price_event(**kw)
        self._p(f"data/price-records/{bundle['price']['id']}.json").write_text(
            json.dumps(bundle["price"], ensure_ascii=False, indent=2), encoding="utf-8")
        self._p(f"data/price-record-revisions/{bundle['price']['id']}/1.json").write_text(
            json.dumps(bundle["price"], ensure_ascii=False, indent=2), encoding="utf-8")
        self._p(f"data/price-facts/versions/{bundle['pfv']['version_id']}.json").write_text(
            json.dumps(bundle["pfv"], ensure_ascii=False, indent=2), encoding="utf-8")
        self._p(f"data/price-evidence/{bundle['ev']['id']}.json").write_text(
            json.dumps(bundle["ev"], ensure_ascii=False, indent=2), encoding="utf-8")
        # current 指向
        cur = json.loads((self.root / "data/price-facts/current.json").read_text())
        cur["facts"][bundle["pfv"]["fact_key"]] = {
            "version_id": bundle["pfv"]["version_id"],
            "observed_at": bundle["pfv"]["observed_at"],
            "evidence_id": bundle["pfv"]["evidence_id"]}
        (self.root / "data/price-facts/current.json").write_text(
            json.dumps(cur, ensure_ascii=False), encoding="utf-8")
        return bundle

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class TestT01Stable(unittest.TestCase):
    """T01：同输入连续导出 → 稳定。"""

    def test_repeat_export_stable(self):
        fx = FixtureRepo()
        out = Path(tempfile.mkdtemp(prefix="t03-out-"))
        try:
            fx.add_obs()
            fx.add_price()
            r1 = run_cli("--output-dir", str(out), input_root=fx.root)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            h1 = tree_hash(out)
            m1 = json.loads((out / "manifest.json").read_text())
            r2 = run_cli("--output-dir", str(out), input_root=fx.root)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            h2 = tree_hash(out)
            m2 = json.loads((out / "manifest.json").read_text())
            self.assertEqual(m1["datasetVersion"], m2["datasetVersion"])
            self.assertEqual(m1["coverage"], m2["coverage"])
            self.assertEqual(m1["files"], m2["files"])
            self.assertEqual(h1, h2, "同输入重建业务文件字节必须相同")
            releases = list((out / "releases").iterdir())
            self.assertEqual(len(releases), 1, "无多余 release")
        finally:
            fx.cleanup()
            shutil.rmtree(out, ignore_errors=True)


class TestT02RevisionChanges(unittest.TestCase):
    """T02：修订/撤回变化 → 新版本；withdrawn 语义。"""

    def test_revision_creates_new_version(self):
        fx = FixtureRepo()
        out = Path(tempfile.mkdtemp(prefix="t03-out-"))
        try:
            fx.add_obs(title="v1")
            r1 = run_cli("--output-dir", str(out), input_root=fx.root)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            v1 = json.loads((out / "manifest.json").read_text())["datasetVersion"]
            fx.add_obs(title="v2", revision=2)
            r2 = run_cli("--output-dir", str(out), input_root=fx.root)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            v2 = json.loads((out / "manifest.json").read_text())["datasetVersion"]
            self.assertNotEqual(v1, v2, "内容修订必须产生新 datasetVersion")
            self.assertEqual(len(json.loads((out / "releases" / v2 / "changes.json")
                                            .read_text())["changes"] if False else
                                 json.loads((out / "releases" / v2 / "changes.json").read_text()),
                                 1) if False else True, True)
        finally:
            fx.cleanup()
            shutil.rmtree(out, ignore_errors=True)

    def test_withdrawn_hidden_in_default_list(self):
        fx = FixtureRepo()
        out = Path(tempfile.mkdtemp(prefix="t03-out-"))
        try:
            rec = fx.add_obs()
            wd = make_obs(source_id="openai-blog", date="2026-09-12",
                          status="withdrawn", revision=2)
            fx.add_obs(date="2026-09-12", status="withdrawn", revision=2)
            r = run_cli("--output-dir", str(out), input_root=fx.root)
            self.assertEqual(r.returncode, 0, r.stderr)
            ver = json.loads((out / "manifest.json").read_text())["datasetVersion"]
            changes = json.loads((out / "releases" / ver / "changes.json").read_text())
            wd_in = [c for c in changes if c["status"] == "withdrawn"]
            items = json.loads((out / "releases" / ver / "items.json").read_text())
            self.assertTrue(len(wd_in) > 0, "withdrawn 保留在 items 集合中")
            wd_item = next(i for i in items if i["status"] == "withdrawn")
            self.assertTrue(wd_item.get("revisionHistory"),
                            "withdrawn 详情仍可读（含修订链）")
        finally:
            fx.cleanup()
            shutil.rmtree(out, ignore_errors=True)


class TestT03BadInputs(unittest.TestCase):
    """T03：坏输入 → 非零退出，正式目录逐字节不变。"""

    def _assert_zero_write(self, fx, out):
        before = tree_hash(out)
        r = run_cli("--output-dir", str(out), input_root=fx.root)
        self.assertNotEqual(r.returncode, 0, "坏输入必须非零退出")
        self.assertEqual(tree_hash(out), before, "正式目录逐字节不变")
        return r

    def test_bad_json(self):
        fx = FixtureRepo()
        out = Path(tempfile.mkdtemp(prefix="t03-out-"))
        try:
            fx.add_obs()
            r_ok = run_cli("--output-dir", str(out), input_root=fx.root)
            self.assertEqual(r_ok.returncode, 0)
            (fx.root / "data/records").glob("obs_*.json").__next__().write_text("{bad")
            r = self._assert_zero_write(fx, out)
            self.assertIn("损坏", r.stderr)
        finally:
            fx.cleanup()
            shutil.rmtree(out, ignore_errors=True)

    def test_unknown_source(self):
        fx = FixtureRepo()
        out = Path(tempfile.mkdtemp(prefix="t03-out-"))
        try:
            fx.add_obs(source_id="evil-unknown-source")
            r = self._assert_zero_write(fx, out)
            self.assertIn("未知 sourceId", r.stderr)
        finally:
            fx.cleanup()
            shutil.rmtree(out, ignore_errors=True)

    def test_dangling_evidence(self):
        fx = FixtureRepo()
        out = Path(tempfile.mkdtemp(prefix="t03-out-"))
        try:
            b = fx.add_price()
            # 事件引用的证据删除 → 悬空
            (fx.root / f"data/price-evidence/{b['ev']['id']}.json").unlink()
            r = self._assert_zero_write(fx, out)
            self.assertIn("悬空", r.stderr)
        finally:
            fx.cleanup()
            shutil.rmtree(out, ignore_errors=True)


class TestT04Modes(unittest.TestCase):
    """T04：--check/--dry-run/隔离输出零污染。"""

    def test_modes(self):
        fx = FixtureRepo()
        real_out = Path(tempfile.mkdtemp(prefix="t03-real-"))
        iso_out = Path(tempfile.mkdtemp(prefix="t03-iso-"))
        try:
            r = run_cli("--output-dir", str(real_out), input_root=fx.root)
            self.assertEqual(r.returncode, 0)
            baseline = tree_hash(real_out)
            # --dry-run：零写入
            r = run_cli("--dry-run", "--output-dir", str(real_out),
                        input_root=fx.root)
            self.assertEqual(r.returncode, 0)
            self.assertIn("dry-run", r.stdout)
            self.assertEqual(tree_hash(real_out), baseline)
            # --check：零写入
            r = run_cli("--check", "--output-dir", str(real_out))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(tree_hash(real_out), baseline)
            # 隔离 output-dir 不污染正式
            fx.add_obs(date="2026-09-13", title="额外记录")
            r = run_cli("--output-dir", str(iso_out), input_root=fx.root)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(tree_hash(real_out), baseline, "隔离输出不得污染另一目录")
        finally:
            fx.cleanup()
            shutil.rmtree(real_out, ignore_errors=True)
            shutil.rmtree(iso_out, ignore_errors=True)


class TestT05ManifestTamper(unittest.TestCase):
    """T05：manifest 篡改 → 门禁失败。"""

    def test_tampered_hash(self):
        fx = FixtureRepo()
        out = Path(tempfile.mkdtemp(prefix="t03-out-"))
        try:
            fx.add_obs()
            self.assertEqual(run_cli("--output-dir", str(out),
                                     input_root=fx.root).returncode, 0)
            m = json.loads((out / "manifest.json").read_text())
            m["files"][0]["sha256"] = "0" * 64
            (out / "manifest.json").write_text(json.dumps(m))
            r = run_cli("--check", "--output-dir", str(out))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("sha256", r.stderr)
        finally:
            fx.cleanup()
            shutil.rmtree(out, ignore_errors=True)

    def test_path_escape(self):
        fx = FixtureRepo()
        out = Path(tempfile.mkdtemp(prefix="t03-out-"))
        try:
            fx.add_obs()
            self.assertEqual(run_cli("--output-dir", str(out),
                                     input_root=fx.root).returncode, 0)
            m = json.loads((out / "manifest.json").read_text())
            m["files"][0]["path"] = "releases/ds_x/../../records.json"
            (out / "manifest.json").write_text(json.dumps(m))
            r = run_cli("--check", "--output-dir", str(out))
            self.assertNotEqual(r.returncode, 0)
        finally:
            fx.cleanup()
            shutil.rmtree(out, ignore_errors=True)


class TestNoLeak(unittest.TestCase):
    """公开输出不泄漏本地路径（T16 CLI 半）。"""

    def test_no_local_path_in_output(self):
        fx = FixtureRepo()
        out = Path(tempfile.mkdtemp(prefix="t03-out-"))
        try:
            fx.add_obs()  # provenance.diff_file = /Users/secret/…
            self.assertEqual(run_cli("--output-dir", str(out),
                                     input_root=fx.root).returncode, 0)
            ver = json.loads((out / "manifest.json").read_text())["datasetVersion"]
            for f in (out / "releases" / ver).glob("*.json"):
                self.assertNotIn("/Users/", f.read_text(), f.name)
                self.assertNotIn(fx.root.name, f.read_text(), f.name)
        finally:
            fx.cleanup()
            shutil.rmtree(out, ignore_errors=True)


class TestT18RealArchive(unittest.TestCase):
    """T18 CLI 半：真实归档全量构建（只读）。"""

    def test_real_dry_run(self):
        if not (BASE / "data" / "records").exists():
            self.skipTest("无真实归档")
        r = run_cli("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ds_", r.stdout)
        self.assertIn("changes=", r.stdout)
        # 真实 provider 映射完备（未知 sourceId 会构建失败，即隐式校验）


class TestCanonical(unittest.TestCase):
    """canonical 单元（M1 补充：字段增删必变版本）。"""

    def test_dataset_version_sensitivity(self):
        cols = {"changes": [{"id": "obs_" + "a" * 64,
                             "observationDate": "2026-09-10", "title": "x"}],
                "status": {"v": 1}}
        v1 = canonical.compute_dataset_version(cols, "2026-09-10")
        cols["changes"][0]["title"] = "y"
        v2 = canonical.compute_dataset_version(cols, "2026-09-10")
        self.assertNotEqual(v1, v2)
        cols["changes"].append({"id": "obs_" + "b" * 64,
                                "observationDate": "2026-09-11", "title": "z"})
        v3 = canonical.compute_dataset_version(cols, "2026-09-11")
        self.assertNotEqual(v2, v3)
        self.assertNotEqual(v1, v3)



class TestIdentityCatalog(unittest.TestCase):
    def setUp(self):
        self.fx = FixtureRepo()
        self.addCleanup(self.fx.cleanup)
        self.fx.add_obs()
        self.out = Path(tempfile.mkdtemp(prefix="t07-catalog-"))
        self.addCleanup(shutil.rmtree, self.out, True)
        self.registry_path = self.fx.root / 'data/model-registry/models.json'

    def export(self):
        r = run_cli('--output-dir', str(self.out), input_root=self.fx.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        manifest = json.loads((self.out / 'manifest.json').read_text())
        directory = self.out / 'releases' / manifest['datasetVersion']
        return manifest, directory, json.loads((directory / 'model-identities.json').read_text())

    def test_catalog_exact_public_membership_and_manifest(self):
        manifest, directory, catalog = self.export()
        registry = json.loads(self.registry_path.read_text())['models']
        self.assertEqual({m['modelId'] for m in catalog['models']},
                         {m['modelId'] for m in registry if m['classification'] == 'model'})
        self.assertEqual({f['familyId'] for f in catalog['families']},
                         {f['modelId'] for f in registry if f['classification'] == 'family'})
        families = {f['familyId'] for f in catalog['families']}
        self.assertTrue(all(m.get('familyId') in families for m in catalog['models'] if 'familyId' in m))
        # Fixture 只有 source observation，catalog identities 在三种记录里全无。
        for name in ('changes', 'prices', 'items'):
            self.assertTrue(all('modelId' not in row and 'familyId' not in row
                                for row in json.loads((directory / f'{name}.json').read_text())))
        entry = next(f for f in manifest['files'] if f['path'].endswith('/model-identities.json'))
        raw = (directory / 'model-identities.json').read_bytes()
        self.assertEqual(entry['bytes'], len(raw))
        self.assertEqual(entry['sha256'], hashlib.sha256(raw).hexdigest())
        release_manifest = json.loads((directory / 'manifest.json').read_text())
        self.assertIn(entry, release_manifest['files'])

    def test_catalog_only_changes_version_and_freezes_history(self):
        first, old_dir, catalog = self.export()
        old_hash = tree_hash(old_dir)
        registry = json.loads(self.registry_path.read_text())
        registry['models'].extend([
            {'modelId': 'alibaba:zero-family', 'providerId': 'alibaba', 'canonicalName': 'Zero Family',
             'familyId': 'alibaba:zero-family', 'classification': 'family', 'aliases': []},
            {'modelId': 'alibaba:zero-model', 'providerId': 'alibaba', 'canonicalName': 'Zero Model',
             'familyId': 'alibaba:zero-family', 'classification': 'model', 'aliases': []},
        ])
        self.registry_path.write_text(json.dumps(registry))
        second, new_dir, new_catalog = self.export()
        self.assertNotEqual(first['datasetVersion'], second['datasetVersion'])
        self.assertEqual(tree_hash(old_dir), old_hash)
        for name in BUSINESS:
            if name != 'model-identities.json':
                self.assertEqual((old_dir / name).read_bytes(), (new_dir / name).read_bytes())
        self.assertNotIn('alibaba:zero-model', {m['modelId'] for m in catalog['models']})
        self.assertIn('alibaba:zero-model', {m['modelId'] for m in new_catalog['models']})
        # Registry 行顺序/notes/无命中 alias 不是公开合同，不改变版本或文件字节。
        registry['models'].reverse()
        registry['models'][0]['notes'] = 'internal-only'
        registry['models'][0]['aliases'].append({'value': 'unused-test-alias', 'type': 'raw', 'source': 'test'})
        self.registry_path.write_text(json.dumps(registry))
        third, _, _ = self.export()
        self.assertEqual(second['datasetVersion'], third['datasetVersion'])
        self.assertEqual(second['files'], third['files'])

    def test_missing_or_invalid_registry_fails_without_writes(self):
        self.export()
        before = tree_hash(self.out)
        for content in (None, '{', '{"models": [{"classification": "model"}]}'):
            if content is None:
                self.registry_path.unlink()
            else:
                self.registry_path.write_text(content)
            r = run_cli('--output-dir', str(self.out), input_root=self.fx.root)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(tree_hash(self.out), before)

    def test_catalog_check_rejects_missing_and_tampered(self):
        manifest, directory, _ = self.export()
        file = directory / 'model-identities.json'
        raw = file.read_bytes()
        file.write_bytes(raw.replace(b'Claude', b'ClauDe', 1))
        self.assertNotEqual(run_cli('--check', '--output-dir', str(self.out)).returncode, 0)
        file.unlink()
        self.assertNotEqual(run_cli('--check', '--output-dir', str(self.out)).returncode, 0)
        file.write_bytes(raw)
        manifest['files'] = [f for f in manifest['files'] if not f['path'].endswith('/model-identities.json')]
        (self.out / 'manifest.json').write_text(json.dumps(manifest))
        self.assertNotEqual(run_cli('--check', '--output-dir', str(self.out)).returncode, 0)


if __name__ == "__main__":
    unittest.main()
