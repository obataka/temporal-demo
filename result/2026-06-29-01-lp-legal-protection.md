# LP 法的保護追加 — 概要ドキュメント

## A. System Interaction Flow

```
ユーザー（フォーム入力）
  → submit ボタンクリック
    → JS: privacyConsent チェック
      → 未同意: showFormError() で処理終了
      → 同意済み: submitBtn.disabled = true → fetch('/api/contact', ...) → 既存ロジック
フッター or フォーム同意ラベル
  → openPrivacyModal() クリック
    → #privacy-modal を flex 表示
      → 「閉じる」or Escape → closePrivacyModal() で hidden に戻す
```

## B. Responsibility Matrix

| ファイルパス | 変更箇所 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `web-ui/public/lp.html` | `#privacy-modal` 追加 | プライバシーポリシーを表示するモーダル | `openPrivacyModal()` / `closePrivacyModal()` |
| `web-ui/public/lp.html` | `#privacy-consent` チェックボックス追加 | 同意の意思確認（必須） | フォームsubmitバリデーション |
| `web-ui/public/lp.html` | submitボタン下注記に免責事項追記 | AIプロトタイプであること・責任の所在を明示 | — |
| `web-ui/public/lp.html` | フッターにプライバシーポリシーリンク追加 | 個人情報保護法対応の入口を常時表示 | `openPrivacyModal()` |
| `web-ui/public/lp.html` | `openPrivacyModal` / `closePrivacyModal` JS追加 | モーダルの開閉制御 | `#privacy-modal`, `#video-modal` と同パターン |
| `web-ui/public/lp.html` | フォームsubmitバリデーション強化 | 同意なしのsubmitを阻止しエラー表示 | `showFormError()` |

## C. 設計の意図・クリティカルポイント

### なぜこの設計を選んだか
- 既存の `#video-modal` パターンを踏襲することで、新規JSライブラリ不要・デザイン一貫性を維持
- プライバシーポリシーは別ページではなくモーダルにすることで、申し込み文脈を途切れさせない

### クリティカルポイント（最大3点）
1. **同意チェックはJS側でも二重ガード**  
   `required` 属性だけではブラウザ依存。submit イベントハンドラ内で `privacyConsent` を明示チェックし、未同意なら `showFormError()` を呼んで処理を確実に止める。

2. **プライバシーポリシーに実在メールアドレスを記載**  
   `obataka123@gmail.com` を問い合わせ窓口として明記。個人情報保護法では開示請求対応窓口の明示が必要なため、実際に受信できるアドレスであることを確認済み（MEMORY より）。

3. **Escapeキーでの複数モーダル競合に注意**  
   `#video-modal`・`#contact-success-modal`・`#privacy-modal` の3つがEscape閉じを持つ。各モーダルのESCハンドラは自身の `hidden` 状態を確認してから動作するため、同時に複数が開くことはなく競合しない。

## 変更ファイル
- `web-ui/public/lp.html`（1ファイルのみ）
