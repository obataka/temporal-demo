# LinkedIn 投稿案

---

## パターン A：技術特化（アーキテクチャ重視）

AIエージェントを「壊れないシステム」にする3つの設計判断を実装しました。

**課題**
LLM API は本質的に脆弱です。Rate limit、タイムアウト、503 高負荷——これらが発生するたびに誰かが手動で再実行していませんか？

**解決策：Temporal + Prometheus + Grafana**

① **Temporal のRetryPolicy** で LLM 障害を自動吸収
→ コード3行で「最大3回、指数バックオフ」のリトライが完成。夜間対応ゼロ。

② **Interceptor パターン**でメトリクスをビジネスロジックから分離
→ `log_llm_interaction` コンテキストマネージャが全 LLM 呼び出しを透過的に計測。LLM プロバイダを変更してもログ・メトリクス側は無変更。

③ **Prometheus Gauge × PromQL join** でリアルタイムコスト計算
→ `sum by(model) (llm_tokens_total * on(model,type) group_left() llm_price_per_million_tokens)` の1行でモデル別コストが動的に算出される。

全スタックは `docker compose up` 一発で起動。ソースコードは GitHub に公開しています。

https://github.com/obataka/temporal-demo

#LLMOps #Temporal #Prometheus #Grafana #Python #AIAgent #SoftwareArchitecture

---

## パターン B：ビジネス特化（コスト・信頼性重視）

「今月、LLM API にいくら使いましたか？」

この質問にすぐ答えられる組織は、まだ少ないと感じています。

AI 活用が広がるにつれ、見えないコストと見えない障害が経営リスクになっていきます。

今回、この2つを同時に解決するプロトタイプを作りました。

**障害リスク → Temporal で解消**
ワークフローエンジンが状態を永続化するため、LLM API が一時停止しても自動でリトライ・再開します。インフラ担当者の夜間対応が不要になります。

**コスト不透明 → Grafana で解消**
モデル別・用途別のコストがリアルタイムで可視化されます。「gemini-2.5-flash と mock-llm の比較」を実際に動かしたところ、

- Gemini Flash：$0.00055（86%）
- Mock LLM：$0.00004（14%）

がダッシュボード上で即座に反映されました。

LLM の「信頼性」と「説明責任」は、エンタープライズ AI の必須条件になると考えています。

実装の詳細はこちら👇
https://github.com/obataka/temporal-demo

#生成AI #AIエージェント #LLMOps #コスト管理 #DX #エンタープライズAI

---

## パターン C：ストーリー特化（開発の集大成）

深夜2時に LLM エージェントが止まって、手動で再実行した経験はありますか？

私はそれが嫌で、「壊れないAIエージェント」を作ることにしました。

---

**Week 1：土台を作る**
Temporal というワークフローエンジンで LLM 呼び出しをラップしました。これで API 障害が起きても自動リトライされます。ワークフローの状態はデータベースに永続化されるため、サーバーが落ちても処理が消えません。

**Week 2：観測可能にする**
structlog で全 LLM 呼び出しを JSON ログ化し、Prometheus でトークン数・レイテンシ・コストをリアルタイム計測。Grafana のダッシュボードでモデル別のコスト比率が円グラフで見えるようになりました。

**Week 3：比較・発信できる形に**
Mock と Gemini を並列実行して比較するデモワークフローを実装。アーキテクチャ図（Mermaid）、コスト設計書、ブログ記事まで整備して GitHub に公開しました。

---

「動けばいい」から「壊れない・説明できる」へ。

これからの AI 開発に求められる水準は、確実に上がっていると感じています。

ソースコード・ドキュメントはすべて公開中です。
https://github.com/obataka/temporal-demo

#AIエージェント #Temporal #LLMOps #Prometheus #Grafana #生成AI #ソフトウェア設計
