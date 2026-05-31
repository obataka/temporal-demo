# Plan: 差し戻し UI の実装（フロントエンド）

## Context
`POST /api/reject` バックエンドに対応するフロントエンドを実装する。
変更対象は `web-ui/public/index.html` の 1 ファイルのみ。

---

## 変更対象ファイル

| ファイル | 変更内容 |
|---|---|
| `web-ui/public/index.html` | textarea・rejectBtn の追加、JS ロジック追加 |

---

## HTML 変更（section ③ アクション）

### 変更前の構造
```
<button id="approveBtn" disabled>GitHub PR 作成を承認する</button>
<p>説明文</p>
```

### 変更後の構造
```
<!-- フィードバック textarea（ボタン群より上） -->
<textarea id="feedbackInput" disabled
  placeholder="AIへの追加指示や修正要望をここに入力してください（差し戻し時に必須）"
  class="w-full rounded-lg border ... mb-4 min-h-[100px]"
></textarea>

<!-- ボタン行（承認 + 差し戻し を横並び） -->
<div class="flex gap-3">
  <button id="approveBtn" disabled class="flex-1 ...">GitHub PR 作成を承認する</button>
  <button id="rejectBtn"  disabled class="flex-1 ...">修正を指示して差し戻す</button>
</div>
<p>承認すると approve_pr、差し戻すと reject_with_feedback シグナルが送信されます</p>
```

**approve ボタン**: 現行の `w-full` を `flex-1` に変更。有効/無効ロジックは既存 `setApproveEnabled()` を流用。

**reject ボタンの色**:
- 有効時: `bg-rose-500 hover:bg-rose-600 text-white cursor-pointer`
- 無効時: `bg-gray-300 text-gray-500 cursor-not-allowed`

**textarea の色**:
- 有効時: `bg-white border-gray-300 text-gray-800`
- 無効時: `bg-gray-50 border-gray-200 text-gray-400 cursor-not-allowed`

---

## JS 変更

### 追加する変数参照
```js
const feedbackInput = document.getElementById('feedbackInput');
const rejectBtn     = document.getElementById('rejectBtn');
```

### 追加する関数: `setRejectEnabled(enabled)`
- enabled=true: rejectBtn と feedbackInput を活性化し、クラスを上書き
- enabled=false: 非活性化し、グレーアウトクラスを上書き

### 修正する箇所
- `fetchStatus()`: `setApproveEnabled()` 呼び出しの直後に `setRejectEnabled()` を追加
- `approveWorkflow()` 成功時: `setRejectEnabled(false)` と `feedbackInput.value = ''` を追加

### 追加する関数: `rejectWorkflow()`
1. `feedbackInput.value.trim()` が空なら warning トースト → return
2. `POST /api/reject` に `{ workflowId, feedbackComment }` を送信
3. 成功: 「修正指示を送信しました」トースト → textarea クリア → 両ボタン無効化
4. 404/エラー: error トースト → ボタン再有効化
5. finally: ボタンテキストをリセット

### 追加するイベントリスナー
```js
rejectBtn.addEventListener('click', rejectWorkflow);
```

---

## 検証手順
1. `grep -E "^  [a-z]" docker-compose.yaml` でサービス名 `web-ui` を確認
2. `docker compose up --build web-ui -d` で再ビルド・起動
3. `curl http://localhost:3000/health` で `{"status":"ok"}` を確認
4. ブラウザで `http://localhost:3000` を開き、レイアウト・スタイルを目視確認
5. 開発者コンソールに JS エラーがないことを確認
