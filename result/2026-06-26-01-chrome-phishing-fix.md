# 2026-06-26-01 Chrome フィッシング警告対策 — LP フォーム属性の安全化

## A. System Interaction Flow

```
Chrome Safe Browsing AI
  → lp.html を解析
  → <input type="email" id="email" name="email"> を検出
  → ログイン画面と誤認 → フィッシング警告

修正後:
  → <input type="text" id="contact-addr" name="contact-addr"> を確認
  → type・id・name すべて中立キーワード → 警告なし
```

## B. Responsibility Matrix

| ファイルパス | 変更箇所 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `web-ui/public/lp.html` | `id="name"` → `id="fullname"` | お名前フィールドの識別子を中立化 | JS querySelector |
| `web-ui/public/lp.html` | `id="company"` → `id="org-name"` | 会社名フィールドの識別子を中立化 | JS querySelector |
| `web-ui/public/lp.html` | `type="email" id="email" name="email"` → `type="text" id="contact-addr" name="contact-addr"` | メールフィールドをログイン画面の典型パターンから外す | JS querySelector, /api/contact |
| `web-ui/public/lp.html` | `autocomplete="name/organization/email"` 追加 | ブラウザに問い合わせフォームの文脈を明示 | Chrome autofill |
| `web-ui/public/lp.html` (JS) | `querySelector('#name'/'#company'/'#email')` → 新 id に追従 | フォーム値の取得 | `/api/contact` POST |

## C. 監査結果と設計意図

### 監査結果
- `<input type="password">` : **ゼロ件**（プロジェクトファイル全体）
- `password` / `パスワード` 文字列 : **ゼロ件**（HTML・JS・TS）
- 原因は password フィールドではなく **`name="email"` / `id="email"` + vercel.app 無料ドメイン** の組み合わせが Chrome の ML に「資格情報収集フォーム」と判定されていた可能性が高い

### 変更の意図
Chrome の Enhanced Safe Browsing は `id="email"` / `name="email"` という正確一致の属性名をログイン画面の強シグナルとして扱う。これをコンタクトフォームの文脈に合う中立名（`contact-addr`、`fullname`、`org-name`）に変更し、誤分類リスクを下げる。

### クリティカル・ポイント（レビュー急所）
1. **サーバー側インターフェース変化なし**: JS 内で `email: contactAddr` と明示エイリアスしているため、`/api/contact` が受け取る JSON キーは引き続き `email`。`ContactBody.email` の変更は不要。
2. **`type="text"` への変更**: HTML5 のメールバリデーション（`@` 有無チェック等）が無効になる。サーバー側の `EMAIL_REGEX` で引き続き検証されるため機能的問題はないが、フロント UX 上は入力ミスが起きやすくなる点を認識すること。
3. **根本原因は未完全解消**: Vercel.app の無料サブドメインそのものが Google Safe Browsing にリストされていた場合、この変更だけでは解消しない。カスタムドメインへの移行が根本的対策。
