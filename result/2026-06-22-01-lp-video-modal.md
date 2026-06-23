# LP 製品PV動画モーダル再生 + 再生時間修正 + プライバシー監査

## 概要

商用LP `web-ui/public/lp.html` のヒーロー右側にあった**静的プレースホルダー**（クリックしても無反応）を、製品PV動画 `/videos/SOP_Platform_Demo_Final.mp4` を**閲覧を妨げないモーダル**で再生する仕組みに置き換えた。あわせて「デモ動画を見る」系CTA 2箇所も同モーダルへ接続し、表示されていた再生時間（誤：3分40秒）を**実尺 2分3秒（2:03）**へ修正、個人名・屋号表記のプライバシー監査を実施した。

変更は `lp.html` 単一ファイルに閉じる（Tailwind CDN の自己完結HTML。外部CSS/JSは存在しない）。

## A. System Interaction Flow（相互作用図）

```
[ヒーロー プレースホルダー button] ─┐
[CTA①「まずデモ動画を見る(2分3秒)」] ─┼─ onclick ─→ openVideoModal()
[CTA②「実際に動作している画面を見る」] ─┘                │
                                                          ├─ #video-modal.hidden を解除（flex表示）
                                                          ├─ body に overflow-hidden（背景スクロールロック）
                                                          └─ <video id="demo-video">.play()

[× 閉じるボタン] ─┐
[背景オーバーレイ クリック] ─┼─ onclick ─→ closeVideoModal()
[Escape キー (keydown)] ─────┘                │
                                              ├─ video.pause() + video.currentTime = 0（確実停止・リセット）
                                              ├─ #video-modal を hidden へ
                                              └─ body の overflow-hidden 解除

[動画枠 inner <div>] ─ onclick="event.stopPropagation()" ─→ 枠内クリックでは閉じない（誤閉じ防止）
```

## B. Responsibility Matrix（責任マッピング表）

| ファイルパス | 要素 / 関数 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| web-ui/public/lp.html | ヒーロー `<button>`（旧プレースホルダー, L78） | クリックでモーダル起動。`aria-label` でSR対応 | `openVideoModal()` |
| web-ui/public/lp.html | CTA① `<button>`（L69 付近） | 「まずデモ動画を見る」からモーダル起動 | `openVideoModal()` |
| web-ui/public/lp.html | CTA② `<button>`（L294 付近） | solution節末尾CTAからモーダル起動 | `openVideoModal()` |
| web-ui/public/lp.html | `#video-modal`（DOM, `</body>`直前） | 16:9枠・`<video>`・閉じる導線を内包するオーバーレイ | `<video#demo-video>` |
| web-ui/public/lp.html | `openVideoModal()` | 表示・スクロールロック・再生開始 | `#video-modal`, `#demo-video` |
| web-ui/public/lp.html | `closeVideoModal()` | 再生停止・リセット・非表示・ロック解除 | `#video-modal`, `#demo-video` |
| web-ui/public/lp.html | `keydown` リスナ | Escape での閉じる経路 | `closeVideoModal()` |

## C. Change Intent & Critical Points（設計の意図）

設計意図:
- **モーダル方式**を採用（BtoB向けに過度なアニメ無し。背景は `bg-slate-950/90 backdrop-blur-sm`、opacity トランジションのみの硬派なトーン）。
- `aspect-video` + `<video class="object-contain">` で **16:9を維持し右上テロップが見切れない**。`object-contain` によりどの画面比でも全フレームをレターボックス表示。
- `preload="none"` で **37MB をモーダルを開くまでダウンロードしない**（初期表示の体感速度を保護）。
- `muted` デフォルト + ネイティブ `controls` で **音声ON/OFFをユーザー操作で可能**に。

レビューで見ておくべき急所（最大3点）:
1. **`closeVideoModal()` の確実停止**: `pause()` に加え `currentTime = 0` を実行。×・背景・Escape の全経路が同関数を通るため、閉じれば必ず音が止まりリセットされる。
2. **誤閉じ防止**: オーバーレイに `closeVideoModal()`、内側の動画枠 `<div>` に `event.stopPropagation()`。動画コントロール操作中に背景クリック判定で閉じない。
3. **プライバシー/屋号の二層化**: 表示コピーは「SOP Platform Labs」（L459, L584）を維持し、`aria-label` 等の機械可読識別子のみ `SOP_Platform_Labs` を使用。個人名（Obara/小原/obataka）は混入ゼロ。

## 検証結果（すべて合格）

| 検証 | コマンド | 結果 |
| :--- | :--- | :--- |
| HTML構文（ExitCode 0厳守） | `python3 -c "...HTMLParser().feed(...)"` | **PARSE OK / exit=0** |
| 個人名監査 | `grep -niE "obara|小原|obataka"` | CLEAN（検出ゼロ） |
| 旧再生時間の残存 | `grep -nE "3:40|3 ?分 ?40"` | CLEAN（残存ゼロ） |
| 新再生時間 | `grep -nE "2:03|2 ?分 ?3"` | L71/78/96/295/608 に反映 |
| 屋号表記 | `grep -noE "SOP_Platform_Labs|SOP Platform Labs"` | 表示=スペース2件 / 識別子=アンダースコア3件 |
| 動画パス整合 | `grep -oE '/videos/...\.mp4'` ↔ `ls videos/` | 一致（SOP_Platform_Demo_Final.mp4） |

## 関連

- plan: `plan/2026-06-22-01-lp-video-modal-plan.md`
