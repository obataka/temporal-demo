# package.json に "type": "module" を追加

## 原因

Vercel エラーログ:
```
SyntaxError: Cannot use import statement outside a module
```

`tsconfig.json` で `"module": "ES2022"` を指定したため esbuild が ESM 形式で出力するが、
`package.json` に `"type": "module"` がなく Node.js が CJS として読もうとしてクラッシュ。

## 変更内容

`web-ui/package.json` に `"type": "module"` を1行追加。

## 副作用なし

- Bun (`src/index.ts`): ESM ネイティブ対応のため影響なし
- コード内に CommonJS `require()` 呼び出しなし
