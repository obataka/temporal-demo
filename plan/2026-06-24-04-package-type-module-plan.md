# Plan: package.json に "type": "module" を追加して ESM エラーを解消

## Context

Vercel エラーログ: `SyntaxError: Cannot use import statement outside a module`

`tsconfig.json` の `"module": "ES2022"` により ESM 形式の `.js` が出力されるが、
`web-ui/package.json` に `"type": "module"` がなく Node.js が CJS として読もうとしてクラッシュ。

## 変更

`web-ui/package.json` に `"type": "module"` を1行追加するだけ。

## 副作用なし

- `src/index.ts`（Bun）: ESM ネイティブ対応のため影響なし
- コード内に `require()` なし
