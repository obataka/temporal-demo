# LP 製品PV動画モーダル再生 + プライバシー監査

## Context

商用LP `web-ui/public/lp.html` のヒーローセクション右側には現在、再生ボタン風の**静的プレースホルダー**（lines 78–97）が置かれているだけで、クリックしても何も起きない。先日 `web-ui/public/videos/SOP_Platform_Demo_Final.mp4`（37MB の製品PV）を配置済みのため、このプレースホルダーと「デモ動画を見る」系CTAから、当該動画を**閲覧を妨げないモーダルウィンドウ**で再生できるようにする。あわせて、LP内に個人名が混入していないこと・屋号表記が一貫していることを監査する。

`lp.html` は Tailwind CDN を読み込む単一の自己完結HTMLで、外部CSS/JSファイルは存在しない。よって変更は **`lp.html` 1ファイルに閉じる**（インライン `<script>` を追加）。

## 屋号・プライバシー方針（ユーザー確認済み）

- **表示コピー**: 「SOP Platform Labs」（スペース区切り）のまま維持（BtoBの見栄え優先）。
- **機械可読な識別子のみ**: 動画の `aria-label` / `alt` 等に `SOP_Platform_Labs`（アンダースコア）を使用。
- **個人名**: `Obara` / `小原` / `obataka` 等は一切混入させない（現状grepでも検出ゼロを確認済み）。

## 実装方針

### 1. ヒーローのプレースホルダーをモーダル起動トリガーへ（lines 78–97）
- 外側 `<div class="... cursor-pointer">` を **`<button type="button">`** に変更し、`onclick="openVideoModal()"`・`aria-label="SOP_Platform_Labs デモ動画を再生"` を付与（キーボード/スクリーンリーダ対応）。
- 既存のグラデーション・再生ボタン・コーナーラベル（LIVE / 3:40）等の見た目はそのまま流用する。

### 2. 「デモ動画を見る」系CTAも同じモーダルを開く
- line 69 「まずデモ動画を見る（3 分 40 秒）」: `<a href="#solution">` → `<button type="button" onclick="openVideoModal()">`（スタイルクラスは流用）。
- line 291 付近「実際に動作している画面を見る（デモ動画：3分40秒）」: 同様に `href="#hero"` のアンカーをモーダル起動ボタンへ。

### 3. モーダル本体を `</body>` 直前に追加
- 固定オーバーレイ: `fixed inset-0 z-[100] hidden`、背景 `bg-slate-950/90 backdrop-blur-sm`（BtoBの硬派なトーン、過度な装飾なし）。`opacity` の軽いトランジションのみ。
- 中央に **16:9 を維持**するレスポンシブ枠: `aspect-video` + `max-w-5xl w-full mx-auto`。
- `<video>`: `src="/videos/SOP_Platform_Demo_Final.mp4"`、`muted`（デフォルトミュート）、`controls`（ネイティブコントロールで音声ON/OFF可能）、`playsinline`、`preload="none"`（37MBをモーダルを開くまでダウンロードしない）。`class="w-full h-full object-contain bg-black"` で**右上テロップが見切れない**よう全フレーム表示。
- 閉じるボタン（×）を枠右上に配置。

### 3.5. 再生時間表記を実尺（2分3秒）へ修正
実動画は **2:03**。現状「3:40 / 3 分 40 秒」表記の3箇所を修正する:
- line 71 「まずデモ動画を見る（3 分 40 秒）」 → 「（2 分 3 秒）」
- line 95 コーナーラベル `3:40` → `2:03`
- line 294 「（デモ動画：3分40秒）」 → 「（デモ動画：2分3秒）」

### 4. インライン `<script>`（バニラJS、`</body>` 直前）
- `openVideoModal()`: `hidden` 除去、`document.body` のスクロールロック（`overflow-hidden`）、`video.play()`。
- `closeVideoModal()`: **`video.pause()` + `video.currentTime = 0`**（再生確実停止・リセット）、`hidden` 付与、スクロールロック解除。
- 閉じる経路: ×ボタン / 背景クリック（動画枠は `stopPropagation` で誤閉じ防止） / `Escape` キー。

## 変更ファイル

| ファイル | 変更内容 |
| :--- | :--- |
| `web-ui/public/lp.html` | プレースホルダー→ボタン化、CTA2箇所→モーダル起動、モーダルDOM追加、インラインJS追加 |

## 検証

1. **HTML構文チェック（ExitCode 0 を厳守）**:
   `python3 -c "from html.parser import HTMLParser; HTMLParser().feed(open('web-ui/public/lp.html',encoding='utf-8').read()); print('OK')"`
2. **プライバシー監査**: `grep -niE "obara|小原|obataka" web-ui/public/lp.html` → 検出ゼロを確認。
3. **動画パス整合**: `src="/videos/SOP_Platform_Demo_Final.mp4"` が実ファイルと一致することを確認。
4. **目視（任意）**: 静的サーバで配信し、プレースホルダー/CTAクリックでモーダル展開→再生、×・背景・ESCで閉じると再生停止することを確認。

> 注: 承認後、最初の実装ステップとして本プラン内容を CLAUDE.md 規約に従い `plan/2026-06-22-01-lp-video-modal-plan.md` へ永続保存してから実装に着手する（plan モード中はシステム管理ファイルのみ編集可能なため）。
