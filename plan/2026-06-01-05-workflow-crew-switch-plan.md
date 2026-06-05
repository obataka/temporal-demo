# Plan: sop_workflow.py — fix_sop_with_crew_activity への差し替え

## Context

Phase 4 自律修正ループが使う `fix_sop_activity`（単一 Gemini 呼び出し）を、
テストを通過済みの `fix_sop_with_crew_activity`（CrewAI 2 エージェント版）に差し替える。
シグネチャ・戻り値型は同一なので変更点は計 5 行（2 ファイル）のみ。

---

## 変更内容

### sop_workflow.py（3 行変更）

| 行 | 変更前 | 変更後 |
|---|---|---|
| L38 | `import fix_sop_activity` | `import fix_sop_with_crew_activity` |
| L351 (docstring) | `fix_sop_activity を実行して...` | `fix_sop_with_crew_activity を実行して...` |
| L359 | `fix_sop_activity,` | `fix_sop_with_crew_activity,` |

引数 `args=[sop_text, failures, human_feedback]` は変更なし（シグネチャ同一）。

### worker.py（2 行変更）

```python
# インポート行: fix_sop_with_crew_activity を追加
from activities.fix_sop_activity import fix_sop_activity, fix_sop_with_crew_activity

# activities リスト: fix_sop_with_crew_activity を追加登録
fix_sop_activity,
fix_sop_with_crew_activity,
```

`fix_sop_activity` は tests/ が直接インポートしているため Worker 登録から除去しない。

---

## 変更ファイル一覧

| ファイル | 操作 | 内容 |
|---|---|---|
| `workflows/sop_workflow.py` | 3 行変更 | import / docstring / execute_activity 引数 |
| `worker.py` | 2 行変更 | `fix_sop_with_crew_activity` のインポートと Worker 登録への追加 |

---

## 実装後の確認手順

```bash
docker cp workflows/sop_workflow.py temporal-worker:/app/workflows/sop_workflow.py
docker cp worker.py temporal-worker:/app/worker.py
docker exec temporal-worker pytest tests/ -v
```

期待: 全テスト（現時点で 43 件）が PASSED
