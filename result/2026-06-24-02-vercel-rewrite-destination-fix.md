# vercel.json rewrites destination 修正

## A. 原因と修正

Vercel が `web-ui/api/index.ts` を `/api/index` として登録するのに対し、
`vercel.json` の `destination` が `/api` のままだったため、リライト先が見つからず 404 になっていた。

## B. 変更内容

| ファイル | 変更 |
|:---|:---|
| `vercel.json` | `destination: "/api"` → `destination: "/api/index"` |

修正前:
```json
{ "source": "/api/(.*)", "destination": "/api" }
```

修正後:
```json
{ "source": "/api/(.*)", "destination": "/api/index" }
```

## C. 確認手順

デプロイ後、Vercel Logs → Vercel Function で `/api/contact` の呼び出しログが記録されることを確認する。
