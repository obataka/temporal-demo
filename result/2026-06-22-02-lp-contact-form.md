# LP 問い合わせフォーム送信機能 + 送信完了モーダル実装

## 概要

`web-ui/public/lp.html` の問い合わせフォームを静的フォームから非同期送信フォームへ改修し、
Bun + Hono バックエンド (`web-ui/src/index.ts`) に `/api/contact` POST エンドポイントを追加した。
受信通知は nodemailer 経由の SMTP メールとして送信。送信先アドレス・SMTP 認証情報はすべて環境変数から読み込む。

## A. System Interaction Flow（相互作用図）

```
[ユーザー フォーム送信]
  └─ submit event (preventDefault)
       ├─ submitBtn.disabled = true, textContent = "送信中..."
       ├─ fetch POST /api/contact  { name, company, email, message, sop_attachment }
       │
       └─ [Hono /api/contact ハンドラ (web-ui/src/index.ts)]
            ├─ バリデーション (name/company/email 必須・長さ・regex)
            │   └─ 失敗 → 400 { error: string }  → フォーム直下にエラー表示
            ├─ NOTIFICATION_EMAIL 未設定
            │   └─ 200 { accepted: true, emailed: false }  ← フォームはこれも成功扱い
            ├─ SMTP 認証情報不完全
            │   └─ 200 { accepted: true, emailed: false }
            └─ nodemailer.createTransport → transporter.sendMail
                ├─ 成功 → 200 { accepted: true, emailed: true }
                │          └─ openContactSuccessModal()  → #contact-success-modal 表示
                └─ 失敗 → 500 { error: "Internal error" }  ← 詳細はサーバーログのみ
                           └─ フォーム直下にエラー表示（個人情報・詳細漏れなし）
```

## B. Responsibility Matrix（責任マッピング表）

| ファイルパス | 要素 / 関数 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| web-ui/package.json | `"nodemailer": "^9.0.0"` | SMTP メール送信ライブラリを依存に追加 | Dockerfile (bun install) |
| web-ui/src/index.ts | `POST /api/contact` | バリデーション・SMTP 送信・環境変数読込 | nodemailer, process.env |
| web-ui/src/index.ts | `EMAIL_REGEX` | メールアドレス形式の簡易検証 | `/api/contact` ハンドラ |
| web-ui/public/lp.html | `#contact-form` | id 付与・action/method 削除 | JS submit ハンドラ |
| web-ui/public/lp.html | `#sop-attachment` チェックボックス | 手順書 Markdown 化代行希望の有無フィールド | fetch ボディ |
| web-ui/public/lp.html | `#submit-btn` | ローディング・disabled 制御 | submit ハンドラ |
| web-ui/public/lp.html | `#form-error` | バリデーション・ネットワークエラーの表示枠 | submit ハンドラ |
| web-ui/public/lp.html | `#contact-success-modal` | 送信完了モーダル DOM（指定文言） | openContactSuccessModal() |
| web-ui/public/lp.html | `openContactSuccessModal / closeContactSuccessModal` | モーダル表示・非表示・スクロールロック | `#contact-success-modal` |
| .env.example | SMTP 環境変数ドキュメント | 必要変数の一覧と説明 | 運用担当者 |

## C. Change Intent & Critical Points（設計の意図）

設計意図:
- バックエンドは既存の Bun + Hono に追加（Vercel/Next.js への移行は不要。URL パスのみ `/api/contact` で揃える）。
- `NOTIFICATION_EMAIL` 未設定・SMTP 認証不完全の場合は **スキップして 200 を返す**。環境未整備でもフロントが壊れない「graceful degradation」設計。

レビューで見ておくべき急所（最大3点）:
1. **SMTP エラーの情報隠蔽**: `catch` 内で `console.error` にのみ詳細を出力し、フロントへは `{ error: "Internal error" }` だけを返す。個人名・アドレス・認証情報の漏れなし。
2. **バリデーションエラーの二重チェック**: フロント側は `fetch` 前に値を取得するだけでサーバー側バリデーションに頼る。400 レスポンスの `data.error` を `#form-error` に表示するが、500 など予期しない形式は汎用メッセージにフォールバック。
3. **送信中の多重送信防止**: `submitBtn.disabled = true` を `fetch` 呼び出し前（`try` ブロック前ではなく `try` の最初）に設定し、`finally` で必ず解除。重複 POST を防ぐ。

## 検証結果

| 検証 | 結果 |
| :--- | :--- |
| HTML parser (ExitCode 0) | **PARSE OK** |
| 個人名 grep | CLEAN（検出ゼロ） |
| `#contact-form`, `#submit-btn` 等 ID 存在確認 | 全 5 ID 確認済み |
| `fetch('/api/contact'` 参照確認 | L732 に存在 |
| `nodemailer` import + `NOTIFICATION_EMAIL` env var | index.ts L4, L161 に存在 |
| nodemailer npm registry | v9.0.1 確認（`npm info nodemailer version`） |
| bun ローカル実行 | bun 未インストール → Docker ビルドで解決 |

## 関連

- plan: `plan/2026-06-22-02-lp-contact-form-plan.md`
