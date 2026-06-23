# マーケティングデモ動画仕様書 作成完了レポート

**タスク：** `docs/marketing_demo_spec.md` 新規作成  
**作成日：** 2026-06-09

---

## A. System Interaction Flow

```
ユーザー要件（ハイブリッドタイムライン指示）
    ↓
brainstorming スキル → プロジェクトコンテキスト探索
    ↓
ARCHITECTURE.md / web-ui/public/index.html / workflows/sop_workflow.py を読み込み
    ↓
動画尺・構成アプローチを確認（AskUserQuestion）
    ↓
docs/marketing_demo_spec.md を Write ツールで作成（493行）
    ↓
grep で見出し階層を検証（#/##/### の一貫性確認）
    ↓
result/2026-06-09-01-marketing-demo-spec.md を作成（本ファイル）
```

---

## B. Responsibility Matrix

| ファイルパス | 役割 | 内容 |
|---|---|---|
| `docs/marketing_demo_spec.md` | メイン成果物 | 3分40秒の撮影コンテ（セクション×タイムコード別の秒単位仕様） |
| `web-ui/public/index.html` | 参照元 | バッジ色・アニメーション・ログ挙動の正確な仕様を確認 |
| `workflows/sop_workflow.py` | 参照元 | フェーズ名（outline/draft/review/autonomous_fix/github_pr）を確認 |
| `ARCHITECTURE.md` | 参照元 | Temporal × LLM × Prometheus の全体像を把握 |

---

## C. 設計の意図とクリティカルポイント

### 設計意図

- **ハイブリッド構成（案A + 案B）：** SaaS 黄金律（Problem → Demo → CTA）の骨格に「Before/After コントラスト」の冒頭フックを融合。企業の意思決定者が論理的に納得しながら感情的に共感できる流れを設計した。
- **モジュール設計：** Section 2（課題構造化 0:15–0:45）を SNS スピンオフ版でカット可能な独立ブロックとして設計。0:45 からダイレクトに始まる SNS 版が成立する。
- **固有名詞ゼロポリシー：** 禁止ワード対応表を仕様書末尾に明記し、撮影・編集担当者が独立して作業できるよう設計。

### クリティカルポイント（最大3点）

1. **1:55–2:15 の倍速演出指示：** ここだけ編集担当への特別指示（1.5〜2倍速 + 固定テロップ）が必要。見落とすと自律ループが「長くて退屈なシーン」になる。
2. **SNS スピンオフ版の切り抜き範囲：** 0:45–2:10（85秒）が最適範囲。末尾の SNS スピンオフ版タイムコード表を参照して編集すること。
3. **Section 4（技術的信頼性）の訴求トーン：** ここで「Temporal = エンタープライズグレード」という印象を刷り込まないと、視聴者は「面白い UI デモ」で止まる。ナレーションが特に重要。
