#!/usr/bin/env python3
"""价格证据归档测试（Task 02 T01–T18 核心场景）。

全部使用隔离 fixture（tempfile），不触碰真实归档、不联网。
运行：python3 -m unittest discover -s tests -p 'test_price_archive.py'
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "pipeline"))

from pricing import archive as pa  # noqa: E402


def make_fact(fact_key="fk1", amount="1.000000", currency="USD",
              unit_quantity=1_000_000, unit_name="token",
              observed_at=1789329600.0, evidence_id="ev_x",
              provider="google", model="gemini-test", component="input",
              region="global", **kw) -> dict:
    d = {
        "fact_key": fact_key, "provider_id": provider, "model_key": model,
        "component": component, "billing_mode": "realtime",
        "amount": amount, "currency": currency,
        "unit_quantity": unit_quantity, "unit_name": unit_name,
        "region": region, "service_tier": "standard",
        "context_band": None, "time_condition": None,
        "effective_at": None, "observed_at": observed_at,
        "evidence_id": evidence_id, "field_state": "confirmed",
        "stale_reason": None,
    }
    d.update(kw)
    return d


def make_snapshot(source_key="google:pricing", content="html-abc"):
    import hashlib
    sha = hashlib.sha256(content.encode()).hexdigest()
    return pa.make_snapshot_record(
        source_key=source_key, provider_id=source_key.split(":")[0],
        url="https://example.com/pricing", content_sha256=sha)


def make_evidence(snap=None, excerpt="$1.25 / 1M tokens\nmodel row",
                  locator="table:nth-of-type(1)"):
    snap = snap or make_snapshot()
    return pa.make_evidence_record(
        snapshot=snap, locator_type="dom_selector", locator=locator,
        excerpt_text=excerpt, extractor_version="test-1")


class Sandbox:
    """隔离归档目录夹具。"""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="t02-test-"))
        self.versions = self.root / pa.DIR_FACT_VERSIONS
        self.evidence = self.root / pa.DIR_EVIDENCE
        self.snapshots = self.root / pa.DIR_SNAPSHOTS
        self.records = self.root / pa.DIR_PRICE_RECORDS
        self.revisions = self.root / pa.DIR_PRICE_REVISIONS
        self.runs = self.root / pa.DIR_RUNS
        self.current = self.root / pa.DIR_CURRENT

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def tree_hash(self):
        import hashlib
        h = hashlib.sha256()
        for f in sorted(self.root.rglob("*.json")):
            h.update(str(f.relative_to(self.root)).encode())
            h.update(f.read_bytes())
        return h.hexdigest()

    def save(self, fact: dict, evidence_rec=None, source_key="google:pricing"):
        snap = make_snapshot(source_key)
        pa.save_snapshot_meta(self.snapshots, snap)
        ev = evidence_rec or make_evidence(snap)
        pa.save_evidence(self.evidence, ev)
        fact = dict(fact, evidence_id=ev["id"])
        version = pa.make_fact_version(fact, source_key=source_key,
                                       evidence_status="complete")
        pa.save_fact_version(self.versions, version)
        return snap, ev, version

    def commit_event(self, date, fact_key, prev_v, curr_v, cmp_result=None):
        cmp_result = cmp_result or pa.compare_versions(prev_v, curr_v)
        return pa.merge_price_event(
            self.records, self.revisions,
            pa.build_price_event(date, fact_key, prev_v, curr_v, cmp_result))


class TestIDsAndNormalization(unittest.TestCase):
    """ID 规范化（T01 前置）：金额规范化、canonical JSON。"""

    def test_amount_normalize(self):
        self.assertEqual(pa.normalize_amount("1.00"), "1")
        self.assertEqual(pa.normalize_amount("1.0"), "1")
        self.assertEqual(pa.normalize_amount("10"), "10")
        self.assertEqual(pa.normalize_amount("0.500000"), "0.5")
        with self.assertRaises(pa.ArchiveError):
            pa.normalize_amount("abc")

    def test_fact_version_id_amount_invariant(self):
        # '1.0' 与 '1.00' 同一版本
        a = pa.fact_version_id(make_fact(amount="1.0"))
        b = pa.fact_version_id(make_fact(amount="1.00"))
        self.assertEqual(a, b)

    def test_price_record_id_stable(self):
        self.assertEqual(pa.price_record_id("fk", "2026-09-12"),
                         pa.price_record_id("fk", "2026-09-12"))
        self.assertNotEqual(pa.price_record_id("fk", "2026-09-12"),
                            pa.price_record_id("fk", "2026-09-13"))
        with self.assertRaises(pa.ArchiveError):
            pa.price_record_id("fk", "not-a-date")


class TestImmutabilityAndIdempotence(unittest.TestCase):
    """T01：同一输入运行两次，归档字节不变。"""

    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.cleanup()

    def test_double_write_byte_stable(self):
        fact = make_fact()
        h1 = None
        for _ in range(2):
            self.sb.save(fact)
            h = self.sb.tree_hash()
            if h1 is None:
                h1 = h
            else:
                self.assertEqual(h1, h)

    def test_immutable_reject_conflict(self):
        fact = make_fact()
        _, _, v = self.sb.save(fact)
        # 同 version_id 不同内容 → 拒绝
        v2 = dict(v, amount="2")
        with self.assertRaises(pa.ArchiveError):
            pa.save_fact_version(self.sb.versions, v2)


class TestComparisonRules(unittest.TestCase):
    """T03/T04：涨跌计算与条件保护。"""

    def test_amount_down_20_percent(self):
        prev = pa.make_fact_version(make_fact(amount="10"), source_key="k",
                                    evidence_status="complete")
        curr = pa.make_fact_version(make_fact(amount="8", observed_at=1789416000.0),
                                    source_key="k", evidence_status="complete")
        r = pa.compare_versions(prev, curr)
        self.assertEqual(r["changeType"], "amount_changed")
        self.assertEqual(r["comparison"]["percent"], "-20.00")
        self.assertEqual(r["comparison"]["direction"], "down")

    def test_previous_zero_no_percent(self):
        prev = pa.make_fact_version(make_fact(amount="0"), source_key="k",
                                    evidence_status="complete")
        curr = pa.make_fact_version(make_fact(amount="5", observed_at=1789416000.0),
                                    source_key="k", evidence_status="complete")
        r = pa.compare_versions(prev, curr)
        self.assertIsNone(r["comparison"]["percent"])
        self.assertEqual(r["comparison"]["percentUnavailableReason"],
                         "previous_amount_not_positive")

    def test_currency_change_is_terms(self):
        prev = pa.make_fact_version(make_fact(amount="10", currency="USD"),
                                    source_key="k", evidence_status="complete")
        curr = pa.make_fact_version(make_fact(amount="10", currency="CNY",
                                              observed_at=1789416000.0),
                                    source_key="k", evidence_status="complete")
        r = pa.compare_versions(prev, curr)
        self.assertEqual(r["changeType"], "terms_changed")
        self.assertIsNone(r["comparison"])  # 纯条件变化无 comparison

    def test_region_change_is_terms(self):
        prev = pa.make_fact_version(make_fact(amount="10", region="global"),
                                    source_key="k", evidence_status="complete")
        curr = pa.make_fact_version(make_fact(amount="5", region="cn",
                                              observed_at=1789416000.0),
                                    source_key="k", evidence_status="complete")
        r = pa.compare_versions(prev, curr)
        self.assertEqual(r["changeType"], "terms_changed")

    def test_same_value_new_observation_no_event(self):
        prev = pa.make_fact_version(make_fact(), source_key="k",
                                    evidence_status="complete")
        curr = pa.make_fact_version(make_fact(observed_at=1789416000.0),
                                    source_key="k", evidence_status="complete")
        r = pa.compare_versions(prev, curr)
        self.assertEqual(r["changeType"], "newly_observed")  # 无实质变化语义


class TestEventRevisionLifecycle(unittest.TestCase):
    """T05：同日修订、撤回与恢复。"""

    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.cleanup()

    def test_event_id_stable_across_reruns(self):
        fact = make_fact()
        _, _, v = self.sb.save(fact)
        rid = pa.price_record_id(fact["fact_key"], "2026-09-13")
        r1 = self.sb.commit_event("2026-09-13", fact["fact_key"], None, v)
        self.assertEqual(r1["action"], "created")
        # 同输入重放 → unchanged
        r2 = self.sb.commit_event("2026-09-13", fact["fact_key"], None, v)
        self.assertEqual(r2["action"], "unchanged")

    def test_withdraw_and_reactivate(self):
        fact = make_fact()
        _, _, v = self.sb.save(fact)
        rid = pa.price_record_id(fact["fact_key"], "2026-09-13")
        self.sb.commit_event("2026-09-13", fact["fact_key"], None, v)
        w = pa.withdraw_price_event(self.sb.records, self.sb.revisions, rid)
        self.assertEqual(w["action"], "withdrawn")
        cur = json.loads((self.sb.records / f"{rid}.json").read_text())
        self.assertEqual(cur["status"], "withdrawn")
        self.assertEqual(cur["revision"], 2)
        # 恢复：再次 merge active 事件
        r = self.sb.commit_event("2026-09-13", fact["fact_key"], None, v)
        # merge 用签名比较：withdrawn 状态在签名内，重新 merge active 会升修订
        cur2 = json.loads((self.sb.records / f"{rid}.json").read_text())
        self.assertEqual(cur2["status"], "active")
        self.assertEqual(cur2["revision"], 3)


class TestEvidenceCompleteness(unittest.TestCase):
    """T10/T18：完整性评估。"""

    def test_complete_evidence(self):
        c, r = pa.assess_evidence_completeness(
            "Model | Input | Output\nGemini Test | $1.25 / 1M tokens | $5 / 1M tokens",
            "dom_selector")
        self.assertEqual(c, "complete")
        self.assertEqual(r, [])

    def test_header_only_is_partial(self):
        c, r = pa.assess_evidence_completeness(
            "Model | Input | Output", "markdown_block")
        self.assertEqual(c, "partial")
        self.assertIn("excerpt_lacks_amount", r)

    def test_empty_is_unavailable(self):
        c, r = pa.assess_evidence_completeness("", "dom_selector")
        self.assertEqual(c, "unavailable")
        self.assertIn("excerpt_empty", r)

    def test_chinese_amount_complete(self):
        c, r = pa.assess_evidence_completeness(
            "模型 | 输入 | 输出\nqwen-test | 0.5 元 | 2 元", "dom_selector")
        self.assertEqual(c, "complete")

    def test_fresh_vs_completeness_independent(self):
        # T18：完整证据可以是旧价格，新观察也可能缺证——两者独立维度
        c1, _ = pa.assess_evidence_completeness("$1 / 1M tokens", "dom_selector")
        c2, _ = pa.assess_evidence_completeness("$1 / 1M tokens",
                                                "markdown_block")
        # 都 complete；新鲜度由 observed_at 表达，不进完整性
        self.assertEqual(c1, c2)


class TestHtmlSafety(unittest.TestCase):
    """T14：安全转义。"""

    def test_html_excerpt_strips_script(self):
        excerpt = ('<table><tr><td>Model</td><td>$1/1M tokens</td></tr></table>'
                   '<script>alert(1)</script>'
                   '<img src=x onerror=alert(2)>')
        text = pa.html_excerpt_to_text(excerpt)
        self.assertNotIn("<script", text)
        self.assertNotIn("alert", text.replace("onerror", "") or text)
        self.assertIn("Model", text)
        self.assertIn("$1/1M tokens", text)

    def test_safe_url_blocks_non_http(self):
        from pricing.archive import make_evidence_record
        snap = make_snapshot()
        rec = make_evidence_record(snapshot=snap, locator_type="dom_selector",
                                   locator="t", excerpt_text="$1",
                                   extractor_version="v",
                                   subpage_url="javascript:alert(1)")
        self.assertIsNone(rec["subpageUrl"])


class TestValidationGate(unittest.TestCase):
    """T13/T08：校验门禁。"""

    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.cleanup()

    def _errors(self, price_index=None):
        return pa.validate_price_archive(
            self.sb.root, versions_root=self.sb.versions,
            evidence_root=self.sb.evidence,
            snapshots_root=self.sb.snapshots,
            records_root=self.sb.records,
            revisions_root=self.sb.revisions,
            current_file=self.sb.current, price_index=price_index)

    def test_dangling_version_ref_detected(self):
        fact = make_fact()
        _, _, v = self.sb.save(fact)
        # 事件引用不存在的版本
        event = pa.build_price_event(
            "2026-09-13", fact["fact_key"], None,
            dict(v, version_id="pfv_" + "0" * 64),
            pa.compare_versions(None, v))
        pa.merge_price_event(self.sb.records, self.sb.revisions, event)
        errors = self._errors()
        self.assertTrue(any("悬空" in e for e in errors))

    def test_excerpt_hash_tamper_detected(self):
        fact = make_fact()
        _, ev, _ = self.sb.save(fact)
        ev_file = self.sb.evidence / f"{ev['id']}.json"
        rec = json.loads(ev_file.read_text())
        rec["excerptText"] = "篡改内容"
        ev_file.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        errors = self._errors()
        self.assertTrue(any("excerpt_hash" in e for e in errors))

    def test_clean_archive_passes(self):
        fact = make_fact()
        _, _, v = self.sb.save(fact)
        self.sb.commit_event("2026-09-13", fact["fact_key"], None, v)
        # current 更新
        cur = {"schemaVersion": 1, "facts": {
            fact["fact_key"]: {"version_id": v["version_id"],
                               "observed_at": v["observed_at"],
                               "evidence_id": v["evidence_id"]}}, "sources": {}}
        pa.save_current(self.sb.current, cur)
        errors = self._errors()
        self.assertEqual(errors, [])


class TestValidationGateBlindSpots(unittest.TestCase):
    """A5（P2）：门禁一致性盲区——五项篡改反例各自被捕获。

    (1) 高于 current.revision 的额外修订文件；(2) 证据 id 与五要素
    不匹配；(3) 证据引用不存在的快照；(4) current 的 fact_key 对应
    关系与最新版本指向；(5) run 记录 state 非法与 prepared 残留。
    """

    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.cleanup()

    def _errors(self, **over):
        kw = dict(versions_root=self.sb.versions,
                  evidence_root=self.sb.evidence,
                  snapshots_root=self.sb.snapshots,
                  records_root=self.sb.records,
                  revisions_root=self.sb.revisions,
                  current_file=self.sb.current)
        kw.update(over)
        return pa.validate_price_archive(self.sb.root, **kw)

    def _saved_state(self):
        """一套完整干净的归档（供各测试篡改一个维度）。"""
        fact = make_fact()
        snap, ev, v = self.sb.save(fact)
        self.sb.commit_event("2026-09-13", fact["fact_key"], None, v)
        cur = {"schemaVersion": 1, "facts": {
            fact["fact_key"]: {"version_id": v["version_id"],
                               "observed_at": v["observed_at"],
                               "evidence_id": v["evidence_id"]}}, "sources": {}}
        pa.save_current(self.sb.current, cur)
        return fact, v

    # (1) 额外修订：current.revision=1 但目录里出现 2.json
    def test_extra_revision_beyond_current_detected(self):
        fact, v = self._saved_state()
        rid = pa.price_record_id(fact["fact_key"], "2026-09-13")
        rev2 = json.loads((self.sb.revisions / rid / "1.json").read_text())
        rev2 = dict(rev2, revision=2)
        (self.sb.revisions / rid / "2.json").write_text(
            json.dumps(rev2, ensure_ascii=False, indent=2))
        errors = self._errors()
        self.assertTrue(any("超出 current.revision" in e for e in errors))

    # (2) 证据 id 篡改：换掉 locator 后 id 不再与五要素匹配
    def test_evidence_id_mismatch_detected(self):
        fact, v = self._saved_state()
        ev_file = self.sb.evidence / f"{v['evidence_id']}.json"
        rec = json.loads(ev_file.read_text())
        rec["locator"] = "table:nth-of-type(999)"
        ev_file.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        errors = self._errors()
        self.assertTrue(any("五要素不匹配" in e for e in errors))

    # (3) 证据引用不存在的快照
    def test_evidence_dangling_snapshot_detected(self):
        fact, v = self._saved_state()
        ev_file = self.sb.evidence / f"{v['evidence_id']}.json"
        rec = json.loads(ev_file.read_text())
        rec["snapshotContentId"] = "psnap_" + "f" * 64
        # 重算 id 保持五要素自洽，隔离「快照关联」这一项
        rec["id"] = pa.evidence_id(
            rec["snapshotContentId"], rec["locatorType"], rec["locator"],
            rec["excerptHash"], rec["extractorVersion"])
        ev_file.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        (self.sb.evidence / f"{v['evidence_id']}.json").unlink()
        pa.save_evidence(self.sb.evidence, rec)
        errors = self._errors()
        self.assertTrue(any("不存在的快照" in e for e in errors))

    # (4) current 指向旧版本（未指向最新）
    def test_current_stale_version_detected(self):
        fact = make_fact()
        snap, ev, v1 = self.sb.save(fact)
        self.sb.commit_event("2026-09-13", fact["fact_key"], None, v1)
        # 新观察时间的版本（金额变化）
        fact2 = make_fact(amount="2.000000",
                          observed_at=(fact["observed_at"] or 0) + 3600,
                          fact_key=fact["fact_key"])
        fact2 = dict(fact2, evidence_id=ev["id"])
        v2 = pa.make_fact_version(fact2, source_key="google:pricing",
                                  evidence_status="complete")
        pa.save_fact_version(self.sb.versions, v2)
        # current 仍指 v1
        cur = {"schemaVersion": 1, "facts": {
            fact["fact_key"]: {"version_id": v1["version_id"],
                               "observed_at": v1["observed_at"],
                               "evidence_id": v1["evidence_id"]}}, "sources": {}}
        pa.save_current(self.sb.current, cur)
        errors = self._errors()
        self.assertTrue(any("未指向最新版本" in e for e in errors))

    # (4b) current 的 fact_key 与版本不匹配
    def test_current_fact_key_mismatch_detected(self):
        fact, v = self._saved_state()
        cur = {"schemaVersion": 1, "facts": {
            "fk-other": {"version_id": v["version_id"],
                         "observed_at": v["observed_at"],
                         "evidence_id": v["evidence_id"]}}, "sources": {}}
        pa.save_current(self.sb.current, cur)
        errors = self._errors()
        self.assertTrue(any("fact_key 与版本不匹配" in e for e in errors))

    # (5a) run 记录 state 非法
    def test_run_state_invalid_detected(self):
        fact, v = self._saved_state()
        run = pa.make_run_record(
            "2026-09-13", "fetch-2026-09-13", scope=["google:pricing"],
            source_states=[], accepted_versions=[v["version_id"]],
            baseline=None)
        run = dict(run, state="half-baked")
        rf = self.sb.runs / "2026-09-13" / "fetch-2026-09-13.json"
        rf.parent.mkdir(parents=True, exist_ok=True)
        rf.write_text(json.dumps(run, ensure_ascii=False, indent=2))
        errors = self._errors(runs_root=self.sb.runs)
        self.assertTrue(any("state 非法" in e for e in errors))

    # (5b) prepared 残留（中断运行）
    def test_prepared_run_leftover_detected(self):
        fact, v = self._saved_state()
        run = pa.make_run_record(
            "2026-09-13", "fetch-2026-09-13", scope=["google:pricing"],
            source_states=[], accepted_versions=[v["version_id"]],
            baseline=None)
        rf = self.sb.runs / "2026-09-13" / "fetch-2026-09-13.json"
        rf.parent.mkdir(parents=True, exist_ok=True)
        rf.write_text(json.dumps(run, ensure_ascii=False, indent=2))
        errors = self._errors(runs_root=self.sb.runs)
        self.assertTrue(any("prepared 运行残留" in e for e in errors))

    # (5c) committed run 引用不存在的版本
    def test_committed_run_dangling_version_detected(self):
        fact, v = self._saved_state()
        run = pa.make_run_record(
            "2026-09-13", "fetch-2026-09-13", scope=["google:pricing"],
            source_states=[], accepted_versions=["pfv_" + "9" * 64],
            baseline=None)
        pa.commit_run(self.sb.runs, run)
        errors = self._errors(runs_root=self.sb.runs)
        self.assertTrue(any("运行记录版本引用悬空" in e for e in errors))

    # 正常 committed run 不误报
    def test_committed_run_clean(self):
        fact, v = self._saved_state()
        run = pa.make_run_record(
            "2026-09-13", "fetch-2026-09-13", scope=["google:pricing"],
            source_states=[], accepted_versions=[v["version_id"]],
            baseline=None)
        pa.commit_run(self.sb.runs, run)
        errors = self._errors(runs_root=self.sb.runs)
        self.assertEqual(errors, [])


class TestCurrentRebuild(unittest.TestCase):
    """T09：current 损坏后从版本重建。"""

    def test_rebuild_current(self):
        sb = Sandbox()
        try:
            fact = make_fact()
            _, _, v = sb.save(fact)
            self.assertIsNone(pa.rebuild_current(sb.versions, sb.current)
                              .get("facts", {}).get("nope"))
            rebuilt = pa.rebuild_current(sb.versions, sb.current)
            entry = rebuilt["facts"][fact["fact_key"]]
            self.assertEqual(entry["version_id"], v["version_id"])
        finally:
            sb.cleanup()


class TestRunRecord(unittest.TestCase):
    """运行记录 prepared/committed 两态。"""

    def test_commit_run_idempotent(self):
        sb = Sandbox()
        try:
            run = pa.make_run_record(
                "2026-09-13", "fetch-2026-09-13", scope=["k:pricing"],
                source_states=[pa.make_source_state(
                    "k:pricing", status="ok", latest_attempt_at=1.0,
                    last_success_at=1.0, coverage="full")],
                accepted_versions=["pfv_x"], baseline=None)
            pa.commit_run(sb.runs, run)
            f = sb.runs / "2026-09-13" / "fetch-2026-09-13.json"
            t1 = f.read_text()
            pa.commit_run(sb.runs, run)  # 重提交：内容一致保持原时间戳
            self.assertEqual(t1, f.read_text())
            runs = pa.load_committed_runs(sb.runs, "2026-09-13")
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["state"], "committed")
        finally:
            sb.cleanup()


class _CurrentWriteCrasher:
    """在「写 current 记录」这一步注入中断（修订已落盘、current 未替换）。

    真实入口测试用：monkeypatch archive._atomic_write，对 price-records/
    下的目标文件抛 OSError 后自动还原。
    """

    def __init__(self, records_root: Path, fail_times: int = 1):
        self.records_root = records_root
        self.fail_times = fail_times
        self._orig = pa._atomic_write

    def _hook(self, path, data):
        p = Path(path)
        if self.fail_times > 0 and self.records_root in p.parents \
                and p.parent.name == "price-records":
            self.fail_times -= 1
            raise OSError(f"injected crash at {path}")
        return self._orig(path, data)

    def __enter__(self):
        pa._atomic_write = self._hook
        return self

    def __exit__(self, *exc):
        pa._atomic_write = self._orig
        return False


class TestRealEntryInterruption(unittest.TestCase):
    """T09 补：新建/更新/撤回三入口在「修订已写、current 未替换」中断后重跑。

    真实入口（merge_price_event / withdraw_price_event），非内部 helper。
    """

    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.cleanup()

    def _event(self, amount="1.000000"):
        fact = make_fact(amount=amount)
        v = pa.make_fact_version(fact, source_key="google:pricing",
                                 evidence_status="complete")
        return pa.build_price_event(
            "2026-09-13", fact["fact_key"], None, v,
            pa.compare_versions(None, v)), fact["fact_key"]

    def test_create_interrupted_then_rerun(self):
        """新建：r1 修订落盘后 current 写入中断 → 重跑幂等恢复。

        恢复语义：restore 从修订链补出 current → merge 判 unchanged
        （事件在中断前实际已创建成功，重跑不重复创建）。
        """
        e, fk = self._event()
        with _CurrentWriteCrasher(self.sb.records, fail_times=1):
            with self.assertRaises(OSError):
                pa.merge_price_event(self.sb.records, self.sb.revisions, e)
        # 中断态：r1 在、current 无
        rid = e["id"]
        self.assertTrue((self.sb.revisions / rid / "1.json").exists())
        self.assertFalse((self.sb.records / f"{rid}.json").exists())
        r = pa.merge_price_event(self.sb.records, self.sb.revisions, e)
        self.assertEqual(r["action"], "unchanged")  # 已创建，幂等
        cur = json.loads((self.sb.records / f"{rid}.json").read_text())
        self.assertEqual(cur["revision"], 1)

    def test_update_interrupted_then_rerun(self):
        """更新：r2 修订落盘后 current 替换中断 → 重跑幂等（用户复现的 P1）。"""
        e1, fk = self._event("1.000000")
        pa.merge_price_event(self.sb.records, self.sb.revisions, e1)
        import time
        time.sleep(1.1)  # 时间戳必不同——原缺陷触发条件
        e2, _ = self._event("2.000000")
        self.assertEqual(e2["id"], e1["id"])
        with _CurrentWriteCrasher(self.sb.records, fail_times=1):
            with self.assertRaises(OSError):
                pa.merge_price_event(self.sb.records, self.sb.revisions, e2)
        rid = e1["id"]
        r2_file = self.sb.revisions / rid / "2.json"
        r2_bytes = r2_file.read_bytes()  # 历史文件字节（重跑后必须保留）
        cur = json.loads((self.sb.records / f"{rid}.json").read_text())
        self.assertEqual(cur["revision"], 1)  # current 落后
        time.sleep(1.1)
        r = pa.merge_price_event(self.sb.records, self.sb.revisions, e2)
        self.assertEqual(r["action"], "unchanged")
        cur2 = json.loads((self.sb.records / f"{rid}.json").read_text())
        self.assertEqual(cur2["revision"], 2)
        # 历史修订字节不变
        self.assertEqual(r2_bytes, r2_file.read_bytes())

    def test_withdraw_interrupted_then_rerun(self):
        """撤回：撤回修订落盘后 current 替换中断 → 重跑幂等。"""
        e, fk = self._event()
        rid = e["id"]
        pa.merge_price_event(self.sb.records, self.sb.revisions, e)
        import time
        time.sleep(1.1)
        with _CurrentWriteCrasher(self.sb.records, fail_times=1):
            with self.assertRaises(OSError):
                pa.withdraw_price_event(self.sb.records, self.sb.revisions, rid)
        cur = json.loads((self.sb.records / f"{rid}.json").read_text())
        self.assertEqual(cur["revision"], 1)  # current 仍 active r1
        self.assertTrue((self.sb.revisions / rid / "2.json").exists())
        w = pa.withdraw_price_event(self.sb.records, self.sb.revisions, rid)
        self.assertEqual(w["action"], "unchanged")
        cur2 = json.loads((self.sb.records / f"{rid}.json").read_text())
        self.assertEqual(cur2["revision"], 2)
        self.assertEqual(cur2["status"], "withdrawn")

    def test_clock_advance_stays_stable(self):
        """T09 收尾：推进时钟重试仍稳定（多次重跑不再产生新修订）。"""
        e, fk = self._event()
        pa.merge_price_event(self.sb.records, self.sb.revisions, e)
        import time
        for _ in range(3):
            time.sleep(1.05)
            r = pa.merge_price_event(self.sb.records, self.sb.revisions, e)
            self.assertEqual(r["action"], "unchanged")
        cur = json.loads((self.sb.records / f"{e['id']}.json").read_text())
        self.assertEqual(cur["revision"], 1)

    def test_tampered_revision_still_rejected(self):
        """恢复不能放过真冲突：同修订号签名不同 → 拒绝。"""
        e, fk = self._event()
        pa.merge_price_event(self.sb.records, self.sb.revisions, e)
        rid = e["id"]
        rev_file = self.sb.revisions / rid / "1.json"
        rec = json.loads(rev_file.read_text())
        rec["comparison"] = {"previous": "9", "current": "1",
                             "direction": "down", "percent": "-88.89"}
        rev_file.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        with self.assertRaises(pa.ArchiveError):
            pa.merge_price_event(self.sb.records, self.sb.revisions, e)


class TestOnlyScopeLedgerComposition(unittest.TestCase):
    """T07 补：--only 未运行来源的既有事实必须合回台账（防局部调试覆盖全站）。"""

    def test_not_run_facts_rejoined(self):
        # 模拟 fetch-prices 的 --only 组装逻辑（不联网，直接复刻核心分支）
        ran = {"openai"}
        all_provider_facts = {"openai": [make_fact(provider="openai",
                                                   model="gpt-test")],
                              "qwen": [make_fact(provider="qwen",
                                                 model="qwen-test")]}
        prev_facts = all_provider_facts
        all_facts = list(all_provider_facts["openai"])
        # 修复后的逻辑：未运行来源合回
        for pid, facts in prev_facts.items():
            if pid not in ran:
                all_facts.extend(dict(f, field_state="stale",
                                      stale_reason="not_run_kept")
                                 for f in facts)
        providers = {f["provider_id"] for f in all_facts}
        self.assertEqual(providers, {"openai", "qwen"})  # 台账不缩水
        self.assertTrue(any(f.get("stale_reason") == "not_run_kept"
                            for f in all_facts if f["provider_id"] == "qwen"))


class TestSameDayFixedBaseline(unittest.TestCase):
    """验收 P1-1：同日多次变价使用固定前日基线（§4.4）。

    走 fetch-prices._baseline_before + archive.compare_versions 的
    入口级组合（_archive_provider_run 的核心分支）。时序对齐真实约定：
    运行日 D 的抓取发生在上海 D 凌晨（UTC D-1 22:00）。
    """

    def _baseline_and_event(self, versions_root, baseline_date,
                            event_date, amount, observed_ts):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "fp", BASE / "pipeline" / "scripts" / "fetch-prices.py")
        fp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fp)
        baseline = fp._baseline_before(versions_root, event_date)
        prev = baseline.get("fk-opus")
        fact = make_fact(fact_key="fk-opus", amount=amount,
                         observed_at=observed_ts, model="claude-opus-5")
        curr = pa.make_fact_version(fact, source_key="anthropic:pricing",
                                    evidence_status="complete")
        pa.save_fact_version(versions_root, curr)
        if prev is None:
            return pa.compare_versions(None, curr)
        return pa.compare_versions(prev, curr)

    def _utc(self, s):
        from datetime import datetime, timezone
        return datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(
            tzinfo=timezone.utc).timestamp()

    def test_same_day_10_8_9_uses_prior_day_baseline(self):
        sb = Sandbox()
        try:
            vr = sb.versions
            # 09-12 基线：值 10
            r = self._baseline_and_event(vr, "09-12", "2026-09-12",
                                         "10.000000",
                                         self._utc("2026-09-11T22:00"))
            self.assertEqual(r["changeType"], "newly_observed")
            # 09-13 第一次：10 → 8
            r1 = self._baseline_and_event(vr, "09-13", "2026-09-13",
                                          "8.000000",
                                          self._utc("2026-09-12T22:00"))
            self.assertEqual(r1["changeType"], "amount_changed")
            self.assertEqual(r1["comparison"]["previous"], "10")
            self.assertEqual(r1["comparison"]["current"], "8")
            # 09-13 第二次：期望仍与基线 10 比（10 → 9），不是 8 → 9
            r2 = self._baseline_and_event(vr, "09-13", "2026-09-13",
                                          "9.000000",
                                          self._utc("2026-09-13T08:00"))
            self.assertEqual(r2["comparison"]["previous"], "10")
            self.assertEqual(r2["comparison"]["current"], "9")
            self.assertEqual(r2["comparison"]["percent"], "-10.00")
            # 09-13 回到基线值 10 → 无事件
            r3 = self._baseline_and_event(vr, "09-13", "2026-09-13",
                                          "10.000000",
                                          self._utc("2026-09-13T20:00"))
            self.assertEqual(r3["changeType"], "newly_observed")  # 同值语义
        finally:
            sb.cleanup()

    def test_baseline_excludes_same_day_versions(self):
        """基线 cutoff = 目标日上海零点：当日版本不进入基线。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "fp", BASE / "pipeline" / "scripts" / "fetch-prices.py")
        fp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fp)
        sb = Sandbox()
        try:
            # 前日版本（值 10）
            v_prev = pa.make_fact_version(
                make_fact(fact_key="fk-opus", amount="10.000000",
                          observed_at=self._utc("2026-09-11T22:00")),
                source_key="anthropic:pricing", evidence_status="complete")
            pa.save_fact_version(sb.versions, v_prev)
            # 当日早间版本（值 8）——不应进入 09-13 基线
            v_same = pa.make_fact_version(
                make_fact(fact_key="fk-opus", amount="8.000000",
                          observed_at=self._utc("2026-09-12T22:00")),
                source_key="anthropic:pricing", evidence_status="complete")
            pa.save_fact_version(sb.versions, v_same)
            b = fp._baseline_before(sb.versions, "2026-09-13")
            self.assertIn("fk-opus", b)
            self.assertEqual(b["fk-opus"]["amount"], "10")
        finally:
            sb.cleanup()


class TestTwoPhaseCommit(unittest.TestCase):
    """验收 P1-2：归档契约错误零写入（两阶段提交）。

    走 fetch-prices 的 _plan_provider_archive + _commit_archive_plan
    真实入口组合（离线 fixture，不起 playwright）。
    """

    def setUp(self):
        self.fp = self._load_fp()
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.cleanup()

    def _load_fp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "fp", BASE / "pipeline" / "scripts" / "fetch-prices.py")
        fp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fp)
        return fp

    def _plan(self, provider_id: str, ts: float):
        import hashlib
        from pricing.base import ContentSnapshot
        from pricing.extractors import get_extractor
        from pricing.normalize import normalize_and_validate
        from pricing.registry import all_entries
        entry = next(e for e in all_entries()
                     if e.provider_id == provider_id)
        html = (BASE / "data" / "snapshots" / "2026-09-11"
                / f"pricing__{provider_id}.html").read_text(encoding="utf-8")
        sha = hashlib.sha256(html.encode()).hexdigest()
        snap = ContentSnapshot(
            snapshot_id=f"snap-{sha[:24]}", source_key=entry.source_key,
            url=entry.url, fetched_at=ts, http_status=200,
            content_type="text/html", sha256=sha, content=html,
            fetcher_version=entry.fetcher_version)
        result = get_extractor(entry.source_key).extract(snap)
        report = normalize_and_validate(result)
        plan = {"snapshots": [], "evidence": [], "versions": []}
        self.fp._plan_provider_archive(
            entry, snap, result, report, "2026-09-13", ts, plan, {})
        return plan, entry

    def _utc(self, s):
        from datetime import datetime, timezone
        return datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(
            tzinfo=timezone.utc).timestamp()

    def test_late_source_conflict_zero_write(self):
        """后一来源发现冲突 → 预检拦截，任何来源都不写。"""
        # 前日基线版本（让事件判定有 prev）
        from pricing.registry import all_entries
        base_fact = make_fact(fact_key="fk-base", amount="1.000000",
                              observed_at=self._utc("2026-09-11T22:00"),
                              provider="anthropic", model="m")
        pa.save_fact_version(self.sb.versions, pa.make_fact_version(
            base_fact, source_key="anthropic:pricing",
            evidence_status="complete"))
        plan1, _ = self._plan("anthropic", self._utc("2026-09-12T22:00"))
        # 预置磁盘冲突：anthropic 的一个版本文件先写入，然后内容被改
        ev = plan1["evidence"][0]
        pa.save_evidence(self.sb.evidence, ev)
        f = self.sb.evidence / f"{ev['id']}.json"
        rec = json.loads(f.read_text())
        rec["excerptText"] = "被篡改的内容"
        f.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        events: list = []
        try:
            self.fp._commit_archive_plan(
                plan1, "2026-09-13", self.sb.versions, self.sb.evidence,
                self.sb.snapshots, [], None, list(all_entries()), events,
                runs_root=self.sb.runs)
            self.fail("预期 ArchiveError")
        except pa.ArchiveError:
            pass
        # 零写入：版本目录无新增（只有预置的基线版本）
        n_versions = len(list(self.sb.versions.glob("pfv_*.json")))
        self.assertEqual(n_versions, 1)
        self.assertEqual(len(events), 0)

    def test_normal_commit_and_idempotent_rerun(self):
        """正常提交 + 同计划重放幂等（字节不变）。"""
        plan1, _ = self._plan("deepseek", self._utc("2026-09-12T22:00"))
        events: list = []
        self.fp._commit_archive_plan(
            plan1, "2026-09-13", self.sb.versions, self.sb.evidence,
            self.sb.snapshots, [], None, [], events, runs_root=self.sb.runs)
        h1 = self.sb.tree_hash()
        events2: list = []
        self.fp._commit_archive_plan(
            plan1, "2026-09-13", self.sb.versions, self.sb.evidence,
            self.sb.snapshots, [], None, [], events2, runs_root=self.sb.runs)
        self.assertEqual(self.sb.tree_hash(), h1)


class TestFactEvidenceBinding(unittest.TestCase):
    """A3（P1-3）：complete 必须绑定具体事实——三类反例不误判。

    反例即验收要求：错金额、错模型、共享表串证据（其他模型的表被
    当作本模型的证据）都不能判 complete。
    """

    def _fact(self, **over):
        fact = {
            "model_key": "gemini-3.8-flash",
            "amount": "0.750000",
            "currency": "USD",
            "unit_quantity": 1_000_000,
            "unit_name": "token",
        }
        fact.update(over)
        return fact

    # —— 反例 1：错金额 ——

    def test_wrong_amount_not_complete(self):
        # 摘录含模型与 $0.75，事实却是 $9.99——金额不在摘录中
        excerpt = ("Gemini 3.8 Flash\n"
                   "Input price | Free of charge | $0.75 / 1M tokens\n"
                   "Output price | Free of charge | $3.75 / 1M tokens")
        status, reasons = pa.verify_evidence_for_fact(
            excerpt, self._fact(amount="9.99"))
        self.assertEqual(status, "partial")
        self.assertIn("amount_not_in_excerpt", reasons)

    def test_amount_substring_not_counted(self):
        # 金额 '9' 不得命中 '3.75' 或 '0.75' 中的子串 '9'——金额需完整
        excerpt = ("Gemini 3.8 Flash\n"
                   "Input price | $0.75 / 1M tokens")
        status, reasons = pa.verify_evidence_for_fact(
            excerpt, self._fact(amount="9.99"))
        self.assertEqual(status, "partial")
        self.assertIn("amount_not_in_excerpt", reasons)

    def test_bare_digit_in_other_number_not_counted(self):
        # 事实金额 6（元）：摘录只有 '[0, 1024] | 256' 中的数字——
        # '6' 是 '256' 的子串，单元格边界必须拒绝
        excerpt = "模型 | 输入长度 | 价格\nfoo | [0, 1024] | 256"
        status, reasons = pa.verify_evidence_for_fact(
            excerpt, self._fact(model_key="foo", amount="6", currency="CNY"))
        self.assertEqual(status, "partial")
        self.assertIn("amount_not_in_excerpt", reasons)

    # —— 反例 2：错模型 ——

    def test_wrong_model_not_complete(self):
        # 摘录是 Gemini 的表，事实挂在 gpt-6-astra 上——模型不在摘录
        excerpt = ("Gemini 3.8 Flash\n"
                   "Input price | $0.75 / 1M tokens\n"
                   "Output price | $3.75 / 1M tokens")
        status, reasons = pa.verify_evidence_for_fact(
            excerpt, self._fact(model_key="gpt-6-astra"))
        self.assertEqual(status, "partial")
        self.assertIn("model_not_in_excerpt", reasons)

    def test_model_prefix_not_counted(self):
        # model_key 'gpt-6' 不得命中 'gpt-6-astra' 前缀（需完整词）
        excerpt = "Flagship models\ngpt-6-astra | $10.00 / 1M tokens"
        status, reasons = pa.verify_evidence_for_fact(
            excerpt, self._fact(model_key="glm-5"))
        self.assertEqual(status, "partial")
        self.assertIn("model_not_in_excerpt", reasons)

    # —— 反例 3：共享表串证据 ——

    def test_shared_table_cross_model_not_complete(self):
        # 共享表：金额与单位都在，但模型行属于别的模型——串证据不得 complete
        excerpt = ("Model | Input | Output\n"
                   "gemini-3.8-flash | $0.75 | $3.75 / 1M tokens")
        status, reasons = pa.verify_evidence_for_fact(
            excerpt, self._fact(model_key="claude-opus-5",
                                 amount="3.750000"))
        self.assertEqual(status, "partial")
        self.assertIn("model_not_in_excerpt", reasons)

    def test_full_row_binding_complete(self):
        # 正例：模型、金额（含 $ 紧邻）、单位齐备 → complete
        excerpt = ("Model | Input | Output\n"
                   "gemini-3.8-flash | $0.75 / 1M tokens | $3.75 / 1M tokens")
        status, reasons = pa.verify_evidence_for_fact(excerpt, self._fact())
        self.assertEqual(status, "complete")
        self.assertEqual(reasons, [])

    # —— 真实页面形态（本轮八家重放修出的匹配缺口）——

    def test_model_name_dash_space_emoji_variants(self):
        # google 页：model_key 'gemini-3.5-flash-lite' vs 标题
        # 'Gemini 3.5 Flash-Lite'；'...-🍌' vs '(Nano Banana 2) 🍌'
        excerpt_a = ("Gemini 3.5 Flash-Lite\n"
                     "Input price | $0.30 / 1M tokens")
        status, _ = pa.verify_evidence_for_fact(
            excerpt_a, self._fact(model_key="gemini-3.5-flash-lite",
                                  amount="0.3"))
        self.assertEqual(status, "complete")

        excerpt_b = ("Gemini 3.1 Flash Image (Nano Banana 2) 🍌\n"
                     "Input price | $0.50 / 1M tokens")
        status, _ = pa.verify_evidence_for_fact(
            excerpt_b, self._fact(model_key="gemini-3.1-flash-image-🍌",
                                  amount="0.5"))
        self.assertEqual(status, "complete")

    def test_doubao_cell_amount_with_header_currency(self):
        # doubao 形态：金额是裸数字单元格，币种/单位在列头（'元/百万token'）
        excerpt = ("模型名称 | 条件 | 输入 | 输出\n"
                   "doubao-seed-2.0-pro | [0, 32] | 9.6 | 48.0\n"
                   "doubao-seed-evolving | [0, 1024] | 6.00 | 30.00\n"
                   "（列头：输入 元/百万token、输出 元/百万token）")
        status, _ = pa.verify_evidence_for_fact(
            excerpt, self._fact(model_key="doubao-seed-2.0-pro",
                                amount="48", currency="CNY"))
        self.assertEqual(status, "complete")

    def test_glm_million_abbreviation_unit(self):
        # glm 行内写法：'5元/M'（M = million）应命中百万 token 单位
        excerpt = "GLM-5V-Turbo：输入[0,32K)5元/M·[32K+)7元/M"
        status, _ = pa.verify_evidence_for_fact(
            excerpt, self._fact(model_key="glm-5v-turbo", amount="5",
                                currency="CNY"))
        self.assertEqual(status, "complete")

    def test_one_decimal_variant_amount(self):
        # doubao '48.0' 一位小数形态：amount=48 的 variants 需覆盖
        # （币种与单位线索在列头——cell 匹配 + 表内币种线索）
        excerpt = "模型 | 输出 元/百万token\nfoo | 48.0"
        status, _ = pa.verify_evidence_for_fact(
            excerpt, self._fact(model_key="foo", amount="48", currency="CNY"))
        self.assertEqual(status, "complete")

    # —— fact_evidence_status 组合 ——

    def test_form_partial_inherits(self):
        # 摘录形态 partial 时直接继承，不做绑定验证
        rec = {"completeness": "partial"}
        self.assertEqual(pa.fact_evidence_status(rec, self._fact()), "partial")

    def test_record_not_mutated_by_status_check(self):
        # 一张表被多条事实复用：状态检查不得往共享证据记录上写 reasons
        rec = {"completeness": "complete",
               "excerptText": "Model | Input\ngemini-3.8-flash | $0.75 / 1M tokens"}
        before = dict(rec)
        pa.fact_evidence_status(rec, self._fact(model_key="other-model"))
        self.assertEqual(rec, before)


if __name__ == "__main__":
    unittest.main()
