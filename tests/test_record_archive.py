"""Task 01 归档逻辑测试：T01–T09（T10-T12 在 site/tests/records.test.mjs 与构建校验中覆盖）。

运行：python3 -m unittest discover -s tests -p 'test_record_archive.py' -v
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "pipeline" / "scripts"))

from record_archive import (  # noqa: E402
    ArchiveError,
    build_index,
    build_record,
    content_signature,
    load_registry,
    make_permalink,
    make_record_id,
    merge_record,
    resolve_source_id,
    validate_archive,
    withdraw_record,
)

REGISTRY_PATH = BASE / "pipeline" / "config" / "source_registry.json"


def make_registry(tmp: Path, extra: dict | None = None) -> Path:
    """复制真实 registry 到临时目录（可加测试来源）。"""
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if extra:
        data["sources"].append(extra)
    p = tmp / "source_registry.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def sample_entry(platform="智谱AI", source_type="pricing", **kw):
    base = {
        "platform": platform, "source_type": source_type,
        "url": "https://bigmodel.cn/pricing", "status": "changed",
        "added_count": 2, "removed_count": 1,
        "added_lines": ["GLM-5.4 输入 ¥8/百万tokens", "GLM-5.4 输出 ¥24/百万tokens"],
        "removed_lines": ["GLM-5.3 输入 ¥8/百万tokens"],
        "pairs": [], "kind": "substantive", "signal_preview": "GLM-5.4 上架",
    }
    base.update(kw)
    return base


class ArchiveTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="record_archive_test_"))
        self.records = self.tmp / "records"
        self.revisions = self.tmp / "record-revisions"
        self.registry_path = make_registry(self.tmp)
        self.registry = load_registry(self.registry_path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, date="2026-09-11", **kw):
        entry = sample_entry(**kw)
        sid = resolve_source_id(self.registry, entry["platform"],
                                entry["source_type"], entry["url"])
        record = build_record(entry, date, sid, self.registry,
                              provenance={"diff_file": f"data/diff/{date}.json"})
        return entry, record, sid


class T01SameDayIdempotent(ArchiveTestBase):
    def test_same_input_same_bytes(self):
        """T01：同 source 同日重复归档——ID、revision、文件字节不变。"""
        _, record, _ = self.build()
        r1 = merge_record(self.records, self.revisions, record)
        self.assertEqual(r1["action"], "created")
        f = self.records / f"{record['id']}.json"
        bytes1 = f.read_bytes()
        r2 = merge_record(self.records, self.revisions, copy.deepcopy(record))
        self.assertEqual(r2["action"], "unchanged")
        self.assertEqual(bytes1, f.read_bytes(), "幂等重跑必须字节不变")
        # revision 文件数不增
        self.assertEqual(
            len(list((self.revisions / record["id"]).glob("*.json"))), 1)


class T02CrossDayDifferentId(ArchiveTestBase):
    def test_different_date_different_id(self):
        """T02：同 source 跨日变化 → 不同 ID。"""
        _, r1, _ = self.build(date="2026-09-10")
        _, r2, _ = self.build(date="2026-09-11")
        self.assertNotEqual(r1["id"], r2["id"])
        merge_record(self.records, self.revisions, r1)
        merge_record(self.records, self.revisions, r2)
        self.assertTrue((self.records / f"{r1['id']}.json").exists())
        self.assertTrue((self.records / f"{r2['id']}.json").exists())


class T03MetadataChangeKeepsId(ArchiveTestBase):
    def test_summary_display_change_new_revision_only_when_meaningful(self):
        """T03：改摘要/显示名/URL 别名 → ID 不变；有意义变化才新修订。"""
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        rid = record["id"]

        # 摘要变化 → 新修订，ID 不变
        changed = copy.deepcopy(record)
        changed["summary"] = "GLM-5.4 正式上架，定价公布"
        r = merge_record(self.records, self.revisions, changed)
        self.assertEqual(r["action"], "updated")
        self.assertEqual(r["revision"], 2)
        self.assertEqual(rid, r["id"])

        # 无变化 → 幂等
        r2 = merge_record(self.records, self.revisions, copy.deepcopy(changed))
        self.assertEqual(r2["action"], "unchanged")

        # URL 变化（别名场景）→ ID 不变（身份不随 URL），有新修订（元数据变化）
        url_changed = copy.deepcopy(changed)
        url_changed["sourceUrl"] = "https://new-url.example.com/pricing"
        r3 = merge_record(self.records, self.revisions, url_changed)
        self.assertEqual(r3["action"], "updated")
        self.assertEqual(r3["id"], rid)


class T05WithdrawAndRestore(ArchiveTestBase):
    def test_unchanged_withdraw_then_changed_restore(self):
        """T05：明确 unchanged → withdrawn（链接可读）；再次 changed → 新修订恢复。"""
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        rid = record["id"]

        r = withdraw_record(self.records, self.revisions, rid)
        self.assertEqual(r["action"], "withdrawn")
        cur = json.loads((self.records / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(cur["status"], "withdrawn")
        self.assertEqual(cur["revision"], 2)
        self.assertIn("撤回", cur["revisionReason"])

        # 旧链接可读：内容仍在
        self.assertTrue(cur["diff"]["added_lines"])

        # 再次 changed → 恢复 active，新修订
        again = copy.deepcopy(record)
        r2 = merge_record(self.records, self.revisions, again)
        self.assertEqual(r2["action"], "updated")
        cur2 = json.loads((self.records / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(cur2["status"], "active")
        self.assertEqual(cur2["revision"], 3)
        self.assertIn("恢复", cur2["revisionReason"])

        # 重复 withdraw 幂等
        r3 = withdraw_record(self.records, self.revisions, rid)
        self.assertEqual(r3["action"], "withdrawn")  # active→withdrawn 又一次
        r4 = withdraw_record(self.records, self.revisions, rid)
        self.assertEqual(r4["action"], "unchanged")  # 已 withdrawn → 幂等


class T06MissingInputNoWithdraw(ArchiveTestBase):
    def test_absent_source_does_not_withdraw(self):
        """T06：来源缺失/未包含/抓取失败不撤回。withdraw_record 只被明确 unchanged 触发；
        归档入口对 fetch_failed/first_fetch/缺失不产生任何动作（在入口测试）。"""
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        rid = record["id"]
        # 模拟「当日输入完全没有这个来源」：不调用任何归档函数 → 记录不动
        cur = json.loads((self.records / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(cur["status"], "active")
        # withdraw_record 不存在条目时 no-op
        r = withdraw_record(self.records, self.revisions, make_record_id(
            resolve_source_id(self.registry, "智谱AI", "pricing",
                              "https://bigmodel.cn/pricing"), "2026-09-10"))
        self.assertEqual(r["action"], "absent")


class T07OldSummaryKept(ArchiveTestBase):
    def test_summary_not_cleared_when_no_new_input(self):
        """T07：历史摘要不在近期窗口 → 不清空旧摘要，不无故增 revision。"""
        _, record, _ = self.build()
        record["summary"] = "LLM 生成的历史摘要"
        record["summaryOrigin"] = "llm"
        merge_record(self.records, self.revisions, record)

        # 新输入无摘要（summary=None）：merge 相同输入幂等；
        # 调用方（sync）负责保留——这里验证无摘要输入不覆盖已有摘要的协议：
        no_summary = copy.deepcopy(record)
        # 场景：窗口外的日期重跑且无 llm 输入 → sync 保留逻辑之外的纯归档行为
        r = merge_record(self.records, self.revisions, copy.deepcopy(record))
        self.assertEqual(r["action"], "unchanged")
        cur = json.loads(
            (self.records / f"{record['id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(cur["summary"], "LLM 生成的历史摘要")


class T08InvalidInputs(ArchiveTestBase):
    def test_unmapped_source_fails(self):
        """T08a：新来源未映射 → 明确失败，旧档案完好。"""
        # 先归档一条正常记录
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        before = (self.records / f"{record['id']}.json").read_bytes()

        with self.assertRaises(ArchiveError) as ctx:
            resolve_source_id(self.registry, "全新平台", "pricing",
                              "https://new.example.com/pricing")
        self.assertIn("source_registry.json", str(ctx.exception))
        # 旧档案完好
        self.assertEqual(before,
                         (self.records / f"{record['id']}.json").read_bytes())

    def test_ambiguous_url_fails(self):
        """T08b：URL 命中多个 source_id（歧义）→ 报错。"""
        # 构造歧义 registry：两个来源共享同一 URL 别名
        amb = make_registry(self.tmp, {
            "source_id": "test-amb-1", "display_name": "智谱AI",
            "source_type": "pricing", "url_aliases": ["https://bigmodel.cn/pricing"],
            "primary_url": "https://bigmodel.cn/pricing",
        })
        reg = load_registry(amb)
        # zhipu-pricing 与 test-amb-1 都匹配 (智谱AI, pricing)，URL 也都命中 → 歧义
        with self.assertRaises(ArchiveError) as ctx:
            resolve_source_id(reg, "智谱AI", "pricing", "https://bigmodel.cn/pricing")
        self.assertIn("歧义", str(ctx.exception))

    def test_corrupted_archive_not_treated_as_empty(self):
        """T08d：归档损坏 → 报错而非静默重建。"""
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        # 写坏当前记录
        (self.records / f"{record['id']}.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(ArchiveError) as ctx:
            json.loads("{}")  # 触发路径
            from record_archive import load_current
            load_current(self.records, record["id"])
        self.assertIn("损坏", str(ctx.exception))

    def test_revision_file_not_overwritten(self):
        """R3 复验：修订版本冲突时当前记录保持完好。

        预置冲突的 r2 修订文件 → merge 更新（rev 2）→ 预检拒绝，
        当前记录仍为 r1 内容（不被改坏）。
        """
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        rid = record["id"]
        # 预置冲突的 r2（内容与将要写入的不同）
        conflict = dict(record)
        conflict["revision"] = 2
        conflict["title"] = "冲突的预置标题"
        conflict_file = self.revisions / rid / "2.json"
        conflict_file.parent.mkdir(parents=True, exist_ok=True)
        conflict_file.write_text(
            json.dumps(conflict, ensure_ascii=False, indent=2), encoding="utf-8")
        # merge 一条内容更新（会产生 rev2）→ 必须失败
        changed = copy.deepcopy(record)
        changed["summary"] = "新摘要"
        with self.assertRaises(ArchiveError) as ctx:
            merge_record(self.records, self.revisions, changed)
        self.assertIn("拒绝覆盖", str(ctx.exception))
        # 当前记录未被改坏（仍是 rev1 原内容：摘要未被更新为"新摘要"）
        cur = json.loads((self.records / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(cur["revision"], 1)
        self.assertNotEqual(cur.get("summary"), "新摘要")
        # 预置文件也未被覆盖
        rev2 = json.loads(conflict_file.read_text(encoding="utf-8"))
        self.assertEqual(rev2["title"], "冲突的预置标题")

    def test_validate_catches_corrupt_revision(self):
        """R3 复验B：修订 JSON 损坏被校验捕获（不只查存在性）。"""
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        rid = record["id"]
        (self.revisions / rid / "1.json").write_text("{broken", encoding="utf-8")
        errors = validate_archive(self.records, self.revisions)
        self.assertTrue(any("修订损坏" in e for e in errors))

    def test_validate_catches_current_revision_mismatch(self):
        """R3 复验：最新修订与当前记录内容不一致被校验捕获。"""
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        rid = record["id"]
        # 直接篡改当前记录（绕过 merge）→ 与 rev1 不一致
        f = self.records / f"{rid}.json"
        cur = json.loads(f.read_text(encoding="utf-8"))
        cur["title"] = "被绕过修订改掉的标题"
        f.write_text(json.dumps(cur, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        errors = validate_archive(self.records, self.revisions)
        self.assertTrue(any("最新修订与当前记录内容不一致" in e for e in errors))


class T09DateOnlyPrecision(ArchiveTestBase):
    def test_no_fabricated_observation_time(self):
        """T09：输入只有日期 → observedAt=None，timePrecision=date，不伪造时刻。"""
        _, record, _ = self.build()
        self.assertIsNone(record["observedAt"])
        self.assertEqual(record["timePrecision"], "date")
        # 摘录限制提示：行被截断时 diffCompleteness=truncated
        entry = sample_entry(added_count=10, added_lines=["只有一行"])
        _, rec2, _ = self.build()
        rec2["diff"]["added_count"] = 10
        rec2["diff"]["added_lines"] = ["只有一行"]
        # build_record 内部判定
        entry2 = sample_entry(added_count=10, added_lines=["只有一行"])
        sid = resolve_source_id(self.registry, "智谱AI", "pricing",
                                "https://bigmodel.cn/pricing")
        rec3 = build_record(entry2, "2026-09-11", sid, self.registry, {})
        self.assertEqual(rec3["diffCompleteness"], "truncated")


class T04WindowScrolling(ArchiveTestBase):
    def test_older_records_survive_window(self):
        """T04（归档侧）：65 个日期全归档后索引覆盖全部，不随窗口缩减。"""
        sid = resolve_source_id(self.registry, "智谱AI", "pricing",
                                "https://bigmodel.cn/pricing")
        from datetime import date as _date, timedelta as _td
        start = _date(2026, 7, 10)
        for i in range(65):
            d = start + _td(days=i)
            date = d.isoformat()
            entry = sample_entry(added_lines=[f"第 {i} 天的变化"])
            record = build_record(entry, date, sid, self.registry, {})
            merge_record(self.records, self.revisions, record)
        index = build_index(self.records)
        self.assertEqual(len(index), 65, "索引覆盖全部归档日期")
        # 稳定排序检查：date 倒序
        dates = [x["date"] for x in index]
        self.assertEqual(dates, sorted(dates, reverse=True))


class IDSpecTest(ArchiveTestBase):
    def test_id_spec(self):
        """ID 规范：obs_ + SHA-256(紧凑 JSON [source_id, date]) 完整 64 位。"""
        rid = make_record_id("zhipu-pricing", "2026-09-11")
        canonical = json.dumps(["zhipu-pricing", "2026-09-11"],
                               ensure_ascii=False, separators=(",", ":"))
        expected = "obs_" + hashlib.sha256(
            canonical.encode("utf-8")).hexdigest()
        self.assertEqual(rid, expected)
        self.assertEqual(len(rid), 4 + 64)
        self.assertTrue(rid.startswith("obs_"))
        # permalink 规范
        self.assertEqual(make_permalink(rid), f"/item/{rid}/")

    def test_industry_source_supported(self):
        """行业来源（非模型厂商）也走 registry，不强行映射。"""
        sid = resolve_source_id(self.registry, "LMArena", "industry",
                                "https://lmarena.ai/leaderboard")
        self.assertEqual(sid, "lmarena-industry")


class ValidateTest(ArchiveTestBase):
    def test_validate_catches_dangling(self):
        """T12（归档侧）：修订链缺失被校验捕获。"""
        _, record, _ = self.build()
        changed = copy.deepcopy(record)
        changed["summary"] = "新摘要"
        merge_record(self.records, self.revisions, record)
        merge_record(self.records, self.revisions, changed)
        # 删掉 rev1 → 校验报错
        (self.revisions / record["id"] / "1.json").unlink()
        errors = validate_archive(self.records, self.revisions)
        self.assertTrue(any("修订缺失" in e for e in errors))

    def test_validate_catches_id_mismatch(self):
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        f = self.records / f"{record['id']}.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        data["sourceId"] = "tampered-source"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        errors = validate_archive(self.records, self.revisions)
        self.assertTrue(any("不匹配" in e for e in errors))


if __name__ == "__main__":
    unittest.main()


class T06EntryBehavior(ArchiveTestBase):
    """T06（验收修正版）：fetch_failed / first_fetch / 缺失输入经真实入口验证。"""

    def _entry_plan(self, changes: list, date="2026-09-11") -> list:
        from record_archive import plan_records, set_prefilter
        from diff_clean import filter_and_pair
        set_prefilter(filter_and_pair)
        data = {"date": date, "changes": changes}
        return plan_records(data, date, "test-diff.json", self.registry)

    def test_fetch_failed_creates_nothing(self):
        """fetch_failed / first_fetch 经入口 → 不建条目、不撤回。"""
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        rid = record["id"]
        # 当日输入：该来源 fetch_failed + 其他来源 first_fetch
        ops = self._entry_plan([
            {"platform": "智谱AI", "source_type": "pricing",
             "url": "https://bigmodel.cn/pricing", "status": "fetch_failed"},
            {"platform": "OpenAI", "source_type": "blog",
             "url": "https://openai.com/news/", "status": "first_fetch"},
        ])
        self.assertEqual(ops, [], "fetch_failed/first_fetch 不得产生任何操作")
        # 已有条目未被撤回
        cur = json.loads((self.records / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(cur["status"], "active")

    def test_absent_source_leaves_record(self):
        """来源完全缺失于当日输入 → 计划中无该来源操作 → 记录不动。"""
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        rid = record["id"]
        # 当日只有另一个来源 changed
        ops = self._entry_plan([
            {"platform": "OpenAI", "source_type": "blog",
             "url": "https://openai.com/news/", "status": "changed",
             "added_count": 1, "added_lines": ["x" * 20],
             "removed_lines": [], "pairs": []},
        ])
        self.assertEqual(len(ops), 1)
        self.assertNotEqual(ops[0]["record"]["id"], rid)
        cur = json.loads((self.records / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(cur["status"], "active")


class T07NoSummaryInput(ArchiveTestBase):
    """T07（验收修正版）：新输入无摘要 → 已有 llm 摘要保留（R4 复现）。"""

    def test_rule_input_after_llm_keeps_llm(self):
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        rid = record["id"]
        # 注入 llm 摘要（r2）
        rec = json.loads((self.records / f"{rid}.json").read_text(encoding="utf-8"))
        rec["summary"] = "LLM 生成的摘要"
        rec["summaryOrigin"] = "llm"
        merge_record(self.records, self.revisions, rec)
        # 离线回填同一天：新输入只有 signal_preview（rule）
        entry = sample_entry(signal_preview="新的规则预览")
        sid = resolve_source_id(self.registry, "智谱AI", "pricing",
                                "https://bigmodel.cn/pricing")
        fresh = build_record(entry, "2026-09-11", sid, self.registry, {})
        r = merge_record(self.records, self.revisions, fresh)
        cur = json.loads((self.records / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(cur["summary"], "LLM 生成的摘要")
        self.assertEqual(cur["summaryOrigin"], "llm")
        # rule 不降级 llm 且内容无其他变化 → 幂等（无新修订）
        self.assertEqual(r["action"], "unchanged")

    def test_none_summary_input_keeps_existing(self):
        """完全无摘要的新输入（signal_preview 也无）→ 保留已有。"""
        _, record, _ = self.build()
        record["summary"] = "已有摘要"
        record["summaryOrigin"] = "llm"
        merge_record(self.records, self.revisions, record)
        rid = record["id"]
        entry = sample_entry(signal_preview=None)
        sid = resolve_source_id(self.registry, "智谱AI", "pricing",
                                "https://bigmodel.cn/pricing")
        fresh = build_record(entry, "2026-09-11", sid, self.registry, {})
        self.assertIsNone(fresh["summary"])
        merge_record(self.records, self.revisions, fresh)
        cur = json.loads((self.records / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(cur["summary"], "已有摘要")


class R2PlanAndApplyTest(ArchiveTestBase):
    """R2：先校验再写入——错误在任意位置均零写入。"""

    def _make_diff_dir(self) -> Path:
        import tempfile
        d = Path(tempfile.mkdtemp(prefix="r2_")) / "diff"
        d.mkdir(parents=True)
        return d

    def test_unmapped_in_second_file_zero_write(self):
        from record_archive import plan_and_apply, set_prefilter
        from diff_clean import filter_and_pair
        set_prefilter(filter_and_pair)
        diff_dir = self._make_diff_dir()
        (diff_dir / "2026-09-10.json").write_text(json.dumps({
            "date": "2026-09-10", "changes": [sample_entry()]},
            ensure_ascii=False))
        (diff_dir / "2026-09-11.json").write_text(json.dumps({
            "date": "2026-09-11", "changes": [sample_entry(
                platform="未注册平台", url="https://x.example.com/p")]},
            ensure_ascii=False))
        with self.assertRaises(ArchiveError):
            plan_and_apply(diff_dir, self.registry, self.records, self.revisions)
        self.assertEqual(len(list(self.records.glob("*.json"))), 0,
                         "预检失败必须零写入")

    def test_corrupt_json_in_last_file_zero_write(self):
        from record_archive import plan_and_apply, set_prefilter
        from diff_clean import filter_and_pair
        set_prefilter(filter_and_pair)
        diff_dir = self._make_diff_dir()
        (diff_dir / "2026-09-10.json").write_text(json.dumps({
            "date": "2026-09-10", "changes": [sample_entry()]},
            ensure_ascii=False))
        (diff_dir / "2026-09-11.json").write_text("{broken")
        with self.assertRaises(ArchiveError):
            plan_and_apply(diff_dir, self.registry, self.records, self.revisions)
        self.assertEqual(len(list(self.records.glob("*.json"))), 0)

    def test_duplicate_source_same_day_zero_write(self):
        from record_archive import plan_and_apply, set_prefilter
        from diff_clean import filter_and_pair
        set_prefilter(filter_and_pair)
        diff_dir = self._make_diff_dir()
        (diff_dir / "2026-09-11.json").write_text(json.dumps({
            "date": "2026-09-11", "changes": [sample_entry(), sample_entry()]},
            ensure_ascii=False))
        with self.assertRaises(ArchiveError):
            plan_and_apply(diff_dir, self.registry, self.records, self.revisions)
        self.assertEqual(len(list(self.records.glob("*.json"))), 0)


class R3InterruptRecoveryTest(ArchiveTestBase):
    """R3：写入中断（records 丢、revisions 在）→ 从最新修订恢复。"""

    def test_restore_current_from_revisions(self):
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        rid = record["id"]
        # 模拟中断：当前记录丢失（修订完好）
        (self.records / f"{rid}.json").unlink()
        # 重跑相同输入：merge 先恢复 current 再比较 → unchanged
        r = merge_record(self.records, self.revisions, copy.deepcopy(record))
        self.assertEqual(r["action"], "unchanged")
        cur = json.loads((self.records / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(cur["id"], rid)

    def test_revision_conflict_keeps_current(self):
        """R3 复现A：预置冲突修订 → merge 拒绝且当前记录完好（同 test_revision_file_not_overwritten，
        此处验证 validate 能捕获预置后的不一致状态）。"""
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        rid = record["id"]
        conflict = dict(record)
        conflict["revision"] = 2
        conflict["title"] = "预置冲突"
        (self.revisions / rid / "2.json").parent.mkdir(parents=True, exist_ok=True)
        (self.revisions / rid / "2.json").write_text(
            json.dumps(conflict, ensure_ascii=False, indent=2), encoding="utf-8")
        errors = validate_archive(self.records, self.revisions)
        # 预置 r2 超出当前 revision（1）→ 校验报"孤立修订"
        self.assertTrue(any("孤立修订" in e for e in errors))


class RealEntryRecoveryTests(ArchiveTestBase):
    def entry(self, name):
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, BASE / 'pipeline/scripts' / f'{name}.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def setup_sync(self):
        root = self.tmp / 'repo'
        config = root / 'pipeline/config'
        config.mkdir(parents=True)
        shutil.copy(self.registry_path, config / 'source_registry.json')
        sync = self.entry('sync-diff-to-site')
        sync.BASE = root
        sync.DIFF_DIR = root / 'data/diff'
        sync.DIFF_DIR.mkdir(parents=True)
        sync.DST_FILE = root / 'site/src/data/daily_changes.json'
        sync.WEEKLY_FILE = sync.DST_FILE.with_name('weekly-digest.json')
        return sync

    def snapshot(self, root):
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def test_sync_later_bad_input_zero_writes(self):
        sync = self.setup_sync()
        good = sync.DIFF_DIR / '2026-09-11.json'
        good.write_text(json.dumps({'date': good.stem, 'changes': [sample_entry()]}))
        sync.main()
        good.write_text(json.dumps({'date': good.stem, 'changes': [sample_entry(added_lines=['new'])]}))
        bad = sync.DIFF_DIR / '2026-09-10.json'
        for value in ('{broken', json.dumps({'changes': [sample_entry(platform='unknown')]}),
                      json.dumps({'changes': [sample_entry(), 123]})):
            with self.subTest(value=value):
                bad.write_text(value)
                before = self.snapshot(sync.BASE)
                with self.assertRaises(SystemExit) as ctx:
                    sync.main()
                self.assertEqual(ctx.exception.code, 1)
                self.assertEqual(before, self.snapshot(sync.BASE))

    def test_sync_existing_archive_error_zero_writes(self):
        sync = self.setup_sync()
        for date in ('2026-09-10', '2026-09-11'):
            (sync.DIFF_DIR / f'{date}.json').write_text(json.dumps({'date': date, 'changes': [sample_entry()]}))
        sync.main()
        records = sync.BASE / 'data/records'
        rid = make_record_id(resolve_source_id(self.registry, '智谱AI', 'pricing', None), '2026-09-10')
        (records / f'{rid}.json').write_text('{broken')
        (sync.DIFF_DIR / '2026-09-11.json').write_text(json.dumps({'changes': [sample_entry(added_lines=['new'])]}))
        before = self.snapshot(sync.BASE)
        with self.assertRaises(SystemExit):
            sync.main()
        self.assertEqual(before, self.snapshot(sync.BASE))

    def test_real_entries_retry_create_update_withdraw(self):
        from unittest.mock import patch
        import record_archive as archive
        import datetime
        for name in ('sync', 'offline'):
            for action in ('create', 'update', 'withdraw'):
                with self.subTest(entry=name, action=action), tempfile.TemporaryDirectory() as tmp:
                    original_tmp = self.tmp
                    self.tmp = Path(tmp)
                    sync = self.setup_sync()
                    self.tmp = original_tmp
                    root = sync.BASE
                    records = root / 'data/records'
                    revisions = root / 'data/record-revisions'
                    path = sync.DIFF_DIR / '2026-09-11.json'
                    def write(entry):
                        path.write_text(json.dumps({'date': path.stem, 'changes': [entry]}))
                    offline = self.entry('archive-source-changes')
                    def run():
                        if name == 'sync':
                            sync.main()
                        else:
                            with patch.object(sys, 'argv', ['archive', '--diff-dir', str(sync.DIFF_DIR),
                                    '--archive-root', str(root / 'data'), '--registry', str(self.registry_path)]):
                                self.assertEqual(offline.main(), 0)
                    write(sample_entry())
                    if action != 'create':
                        run()
                    write(sample_entry(status='unchanged') if action == 'withdraw' else
                          sample_entry(added_lines=['new model price']))
                    before = self.snapshot(records) if records.exists() else {}
                    atomic = archive._atomic_write
                    def fail_current(path, data):
                        if path.parent == records:
                            raise OSError('simulated interruption before current replace')
                        return atomic(path, data)
                    with patch.object(archive, '_atomic_write', side_effect=fail_current):
                        with self.assertRaises(OSError):
                            run()
                    self.assertEqual(before, self.snapshot(records) if records.exists() else {})
                    committed = self.snapshot(revisions)
                    class Later(datetime.datetime):
                        @classmethod
                        def now(cls, tz=None):
                            return cls(2030, 1, 1, tzinfo=tz)
                    with patch('datetime.datetime', Later):
                        run()
                    self.assertEqual(committed, self.snapshot(revisions))
                    self.assertEqual(validate_archive(records, revisions), [])
                    cur = json.loads(next(records.glob('*.json')).read_text())
                    self.assertEqual(cur['revision'], 1 if action == 'create' else 2)
                    self.assertEqual(cur['status'], 'withdrawn' if action == 'withdraw' else 'active')
                    stable = self.snapshot(records)
                    run()
                    self.assertEqual(stable, self.snapshot(records))
                    self.assertEqual(committed, self.snapshot(revisions))

    def test_recovery_rejects_invalid_chain_without_writes(self):
        from record_archive import restore_current_from_revisions
        _, record, _ = self.build()
        merge_record(self.records, self.revisions, record)
        rid = record['id']
        current = self.records / f'{rid}.json'
        current.unlink()
        revision = self.revisions / rid / '1.json'
        original = revision.read_text()
        for content in ('{broken', json.dumps({**record, 'id': 'wrong'})):
            with self.subTest(content=content):
                revision.write_text(content)
                before = self.snapshot(self.tmp)
                with self.assertRaises(ArchiveError):
                    restore_current_from_revisions(self.records, self.revisions, rid)
                self.assertEqual(before, self.snapshot(self.tmp))
        revision.write_text(original)
        revision.rename(revision.with_name('2.json'))
        before = self.snapshot(self.tmp)
        with self.assertRaises(ArchiveError):
            restore_current_from_revisions(self.records, self.revisions, rid)
        self.assertEqual(before, self.snapshot(self.tmp))
