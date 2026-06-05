# E2E 検証結果: マルチエージェント HITL デモ

**実施日時:** 2026-06-02 10:05〜10:11  
**Workflow ID:** `sop-hitl-demo-063a5ac0`  
**総所要時間:** 6.2 分（373 秒）  
**GitHub PR:** https://github.com/obataka/temporal-demo/pull/5

---

## A. System Interaction Flow

```
hitl_webui_demo.py
  → Client.start_workflow(sop_generation_workflow)
      → Phase 1: generate_sop_phase_activity（章立て提案）→ approve_step Signal
      → Phase 2: generate_sop_phase_activity（詳細執筆）  → approve_step Signal
      → Phase 3: generate_sop_phase_activity（最終レビュー）→ approve_step Signal
      → Phase 4（初回）:
          validate_sop_activity → FAIL（TODO含有）
          fix_sop_with_crew_activity [Writer → Reviewer] → 修正済み SOP
          validate_sop_activity → PASS
      → Phase 5 GATE: awaiting_pr_approval（ブラウザ操作待ち）
          ↓ reject_with_feedback Signal（ラウンド1）
      → Phase 4（再実行）:
          fix_sop_with_crew_activity [Writer → Reviewer]（人間フィードバック注入）
          validate_sop_activity（試行 #2）→ PASS
      → Phase 5 GATE: awaiting_pr_approval（ラウンド2）
          ↓ approve_pr Signal
      → GitHubActivity.create_pull_request → PR #5 作成
```

---

## B. Responsibility Matrix

| ファイルパス | クラス/メソッド名 | 処理の目的・役割 | 相互作用する相手 |
|:---|:---|:---|:---|
| `hitl_webui_demo.py` | `main()` | ワークフロー起動・自動承認・ポーリング制御 | `sop_generation_workflow` |
| `hitl_webui_demo.py` | `_wait_for_human_action()` | ブラウザ操作待ち・シグナル検知 | Query `get_status` |
| `hitl_webui_demo.py` | `_poll_phase4()` | Phase 4 進捗リアルタイム表示 | Query `get_status` |
| `workflows/sop_workflow.py` | `sop_generation_workflow` | 全フェーズ制御・Signal/Query ハンドラ | 各 Activity |
| `workflows/sop_workflow.py` | `reject_with_feedback()` | 差し戻しシグナル受信・人間フィードバック保持 | `_call_fix()` |
| `activities/fix_sop_activity.py` | `fix_sop_with_crew_activity()` | CrewAI Writer/Reviewer 2 エージェント直列実行 | Gemini API |
| `activities/fix_sop_activity.py` | `_build_sop_crew()` | Writer・Reviewer Agent / Task 構築 | CrewAI |
| `activities/validate_sop_activity.py` | `validate_sop_activity()` | ルールベース SOP 検証 | — |
| `activities/github_activity.py` | `create_pull_request()` | GitHub PR 作成 | GitHub API |

---

## C. 検証結果サマリー

### 確認できた動作

1. **Phase 1〜3 自動生成・承認**: 各フェーズが Gemini API を介して生成され、`approve_step("")` Signal で正常に次フェーズへ遷移した。

2. **Phase 4 バリデーション→修正ループ（初回）**: 生成 SOP に TODO プレースホルダーが含まれており、`validate_sop_activity` がルール違反を検知。`fix_sop_with_crew_activity` が CrewAI Writer/Reviewer チェーンを実行して修正し、再バリデーションで PASS した。

3. **差し戻し（reject_with_feedback）**: Phase 5 GATE でブラウザから `reject_with_feedback` シグナルを送信。ワークフローがシグナルを検知して Phase 4 を再実行。人間フィードバックが Writer へ注入され、再バリデーション PASS → ラウンド 2 承認待ちへ正常遷移した。

4. **最終承認・PR 作成**: ラウンド 2 で `approve_pr` シグナルを受信後、`GitHubActivity.create_pull_request` が実行され、GitHub PR #5 が作成された。

### タイムライン

| 時刻 | イベント |
|---|---|
| 10:05:35 | ワークフロー起動 |
| 10:05:44 | Phase 1 PASS（9秒） |
| 10:06:23 | Phase 2 PASS（37秒） |
| 10:07:08 | Phase 3 PASS（43秒） |
| 10:07:13〜10:08:59 | Phase 4 初回（バリデーション失敗→修正→PASS、106秒） |
| 10:08:59〜10:09:54 | Phase 5 GATE ラウンド1（55秒待機） |
| 10:09:54〜10:11:04 | Phase 4 再実行（差し戻し→修正→PASS、70秒） |
| 10:11:04〜10:11:49 | Phase 5 GATE ラウンド2（45秒待機） |
| 10:11:49 | PR #5 作成・完了 |

### 観察された注意点

- Phase 2・3 起動直後に `Query エラー（Timeout expired）` が 1 回ずつ発生したが、リトライで即座に回復した。Activity 実行中の Query タイムアウトは既知の挙動であり、動作には影響しない。
- Phase 4 再実行時、`_poll_phase4()` のステータス遷移検出ロジックが `fixing` を直接検知して表示しており、差し戻し経路でも進捗が可視化されることを確認した。
