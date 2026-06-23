# LP フォーム送信 + 送信完了モーダル実装

## Context

`web-ui/public/lp.html` の問い合わせフォームは現状 `action="#" method="post"` の静的フォームで、送信しても何も起きない。
バックエンドに Bun + Hono（`web-ui/src/index.ts`）が存在しているため、同ファイルに `/api/contact` POST ルートを追加し、
フォームデータを SMTP メール通知として受け取る。フロントエンドは非同期送信・ローディング状態・送信完了モーダルを実装する。
（要件では "Vercel/Next.js 想定" とあるが、実態は Bun + Hono + Docker。`/api/contact` の URL 構造だけ合わせ、実装は既存 Hono ルートと同一パターンで行う）

## 変更ファイル一覧

| ファイル | 変更内容 |
| :--- | :--- |
| `web-ui/package.json` | `nodemailer` 依存を追加 |
| `web-ui/src/index.ts` | `POST /api/contact` Hono ルートを追加 |
| `web-ui/public/lp.html` | フォーム非同期送信・ローディング・送信完了モーダル |
| `.env.example` | `NOTIFICATION_EMAIL` 等 SMTP 環境変数ドキュメントを追加 |

## 1. `web-ui/package.json` — nodemailer を追加

```json
"dependencies": {
  "hono": "^4.7.0",
  "@temporalio/client": "^1.16.2",
  "nodemailer": "^9.0.0"
}
```

## 2. `web-ui/src/index.ts` — POST /api/contact

既存の `/api/approve` / `/api/reject` と同じパターンで追加。

**バリデーション**:
- `name`（必須・最大 100 字）、`company`（必須・最大 200 字）、`email`（必須・簡易 regex）が欠けていれば 400 を返す
- `message`（任意・最大 2000 字）、`sop_attachment`（boolean）は任意

**環境変数（すべて `process.env` から読む）**:
| 変数名 | 用途 | 必須 |
| :--- | :--- | :--- |
| `NOTIFICATION_EMAIL` | 通知先メールアドレス | ✅ |
| `SMTP_HOST` | SMTP サーバーホスト | ✅ |
| `SMTP_PORT` | SMTP ポート（デフォルト 587） | - |
| `SMTP_USER` | SMTP 認証ユーザー | ✅ |
| `SMTP_PASS` | SMTP 認証パスワード | ✅ |
| `FROM_EMAIL` | 送信者アドレス（省略時は SMTP_USER） | - |

`NOTIFICATION_EMAIL` が未設定のときはメール送信をスキップして `200 { accepted: true, emailed: false }` を返す（環境未整備でも動作する）。

**レスポンス**:
- `200 { accepted: true }` — 成功
- `400 { error: string }` — バリデーション失敗
- `500 { error: "Internal error" }` — SMTP エラー（詳細はサーバーログのみ。フロントに漏らさない）

## 3. `web-ui/public/lp.html` — フロントエンド変更

### 3a. フォームの変更
- `<form action="#" method="post">` → `<form id="contact-form">` に変更（action/method 削除）
- 送信ボタンに `id="submit-btn"` を付与
- "手順書添付の有無" チェックボックスフィールドを `<textarea>` の下・ボタンの上に追加（`name="sop_attachment"` / `id="sop-attachment"`）

### 3b. 送信完了モーダルの DOM（`#contact-success-modal`）
`#video-modal` の直後、`</body>` 直前に配置。スタイルは video-modal と同系統（`bg-slate-950/90 backdrop-blur-sm`）で硬派・誠実。
モーダル本文:
> お問い合わせを受け付けました。2営業日以内に、SOP Platform Labs 担当より折り返しご連絡いたします。手順書データのMarkdown化代行をご希望の場合は、追ってご案内するセキュアな共有リンクをお待ちください。

### 3c. 既存 `<script>` ブロックへの追加（IIFE 内に追記）
```
contactForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  submitBtn.disabled = true;  // ローディング
  submitBtn.textContent = '送信中...';
  try {
    const res = await fetch('/api/contact', { method: 'POST', body: JSON.stringify({...}) });
    if (res.ok) { openContactSuccessModal(); }
    else { /* エラーメッセージをフォーム直下に表示（個人情報・詳細エラーは含まない） */ }
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = '→ 無償 PoC 枠に申し込む（限定 5 社）';
  }
});

openContactSuccessModal / closeContactSuccessModal は video modal と同パターン。
```

## 4. `.env.example` — ドキュメント追加

既存内容の末尾に以下を追記：
```
# 問い合わせフォーム通知先 (web-ui/api/contact)
NOTIFICATION_EMAIL=your-inbox@example.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-smtp-user
SMTP_PASS=your-smtp-password
FROM_EMAIL=noreply@example.com
```

## 検証

1. **bun install**: `cd web-ui && bun install` — nodemailer が解決されること
2. **HTML構文**: `python3 -c "from html.parser import HTMLParser; HTMLParser().feed(...); print('OK')"` — ExitCode 0
3. **プライバシー監査**: `grep -niE "obara|小原|obataka" web-ui/public/lp.html` — 検出ゼロ
4. **API 動作確認（手動）**:
   ```
   curl -s -X POST http://localhost:3000/api/contact \
     -H "Content-Type: application/json" \
     -d '{"name":"山田太郎","company":"株式会社テスト","email":"test@example.com","message":"テスト"}'
   ```
   → `{"accepted":true}` または `{"accepted":true,"emailed":false}` が返ること
5. **バリデーション確認**: email フィールドを空にして POST → `400` が返ること
