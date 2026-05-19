品質保証の専門家として、提供されたSOP草稿をレビューしました。
全体として、非常に詳細で網羅的、かつ実践的な内容であり、素晴らしい草稿です。特に、Activityの内部動作の詳細な説明、冪等性への言及、多岐にわたるトラブルシューティングは、実用性が高く評価できます。

以下に、【改善点リスト】と、それらを反映した【最終版SOP】を提案します。

---

## 【改善点リスト】

以下の観点から改善点を特定しました。

1.  **用語の明確化と一貫性**
    *   `your_activity_module`: 具体的なファイル名や配置場所の例を提示し、読者が Activity クラスをどこに記述すべきか明確にします。
    *   `GitHubActivity().create_pull_request`: Activity がクラスのインスタンスメソッドとして実装されていること、およびインスタンスを生成して Activity を登録していることを補足します。
    *   `workflow.now()`: Temporal の Workflow 時間はリアルタイムとは異なる場合があるため、補足説明を追加します。

2.  **前提条件と環境準備の具体化**
    *   **Temporal Workerの準備**: Activity コードの具体的な配置例（例: `activities/github_activity.py`）を示し、それを Worker がインポートする方法をより分かりやすくします。
    *   **`GITHUB_TOKEN`の役割**: `git`コマンドでPATがどのように認証に使われるか（URLへの埋め込み）を明確にします。
    *   **`gh CLI`認証のスコープ**: `gh auth login`における認証方法（Webブラウザ/PAT）と、その際に`repo`スコープを付与する手順をより具体的に説明します。

3.  **実用性とトラブルシューティングの強化**
    *   **一時ファイルの管理**: Activity が使用する一時作業ディレクトリ（`_REPO_BASE`などの内部変数名ではなく、一般的な表現で）の場所を明確にし、手動でのクリーンアップ方法（コマンド例）を追記することで、ディスクスペースの問題に対処しやすくします。
    *   **`subprocess.CalledProcessError`のデバッグ**: エラーログ出力例で`stdout`も併せて確認するよう修正し、デバッグの質を高めます。

4.  **その他軽微な修正**
    *   全体的な表現の調整、より簡潔で分かりやすい言い回しへの変更。
    *   Markdownの書式調整（コードブロック内のコメントなど）。
    *   SOPの冒頭で、「実戦疎通テスト用」であることを改めて強調し、本番運用との違いに軽く言及する。

---

## 【最終版SOP】

```markdown
# GitHub PR 作成 Activity 実戦疎通テスト用 SOP

このドキュメントは、Temporal Activityを利用してGitHub上でPull Requestを作成する一連の自動化されたプロセスを、明確かつ実践的に理解し実行するための詳細な標準作業手順書（SOP）です。提供されたPython Activity実装に基づき、GitHubリポジトリへのコードプッシュからプルリクエストの作成までを自動化する手順を詳述します。

---

## 1. はじめに

### 1.1 目的
このSOPは、Temporal Activityとして実装されたGitHub Pull Request作成機能の実戦疎通テストを円滑に実施するための手順を定めます。Temporalワークフローを通じてGitHubリポジトリにコードをプッシュし、プルリクエストを作成する一連のプロセスを自動化し、その信頼性と機能を検証することを目的とします。
**本SOPは、あくまで実戦疎通テストを目的としており、本番運用環境での利用を想定していません。**

### 1.2 対象読者
本SOPの対象読者は、Temporalワークフローの開発者、SRE（Site Reliability Engineer）、およびCI/CDパイプラインの構築・運用に携わるエンジニアです。GitHubの基本的な操作と、Temporalの概念（ワークフロー、アクティビティ、ワーカー）について理解していることを前提とします。

### 1.3 GitHub Pull Request作成Activityの概要
本Activityは、Pythonで実装されたTemporal Activityであり、GitHubのCLIツール (`gh CLI`) とGit CLI (`git CLI`) を利用して、GitHubリポジトリを操作します。具体的には、以下の手順を自動的に実行します。

1.  指定されたGitHubリポジトリをローカルにクローンまたは最新の状態に更新します。
2.  指定されたフィーチャーブランチをチェックアウトし、必要であれば作成します。
3.  指定されたパスにファイルコンテンツを書き込みます。
4.  変更をコミットし、フィーチャーブランチに強制プッシュします。
5.  指定されたタイトルと本文でプルリクエストを作成します。既存の同ブランチからのPRがあれば、そのURLを返します。

このActivityは、Temporalワークフローから呼び出され、GitHubリポジトリに対する一連の操作を冪等性および信頼性を高めるように設計されています。

## 2. 前提条件

このSOPを実行する前に、以下の環境設定、ツール、アカウント、および認証情報が準備されていることを確認してください。

### 2.1 Python実行環境
*   **Python 3.8以上**: Temporal Python SDKの要件を満たすPythonバージョンがインストールされていること。

### 2.2 CLIツール
*   **`git CLI`**: Gitのコマンドラインツールがシステムにインストールされており、パスが通っていること。
    *   インストールガイド: [Git公式ウェブサイト](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
*   **`gh CLI` (GitHub CLI)**: GitHubの公式コマンドラインツールがシステムにインストールされており、パスが通っていること。
    *   インストールガイド: [GitHub CLI公式ウェブサイト](https://cli.github.com/)

### 2.3 Temporal Workerの準備
*   **Temporal Worker**: 提供されたPythonコードに含まれる`GitHubActivity`クラスをホストし、実行できるTemporal Workerが準備されていること。ワーカーはTemporal Serverに接続可能である必要があります。

### 2.4 GitHubアカウントとPersonal Access Token (PAT)
*   **GitHubアカウント**: GitHubリポジトリへの書き込み権限を持つGitHubアカウントが必要です。
*   **GitHub Personal Access Token (`GITHUB_TOKEN`)**: リポジトリへの書き込み権限（`repo`スコープ推奨）を持つPATを生成し、環境変数として設定する必要があります。このトークンは、Gitのプッシュ操作および`gh CLI`によるPR作成操作に使用されます。
    *   PATの生成方法: [GitHub Docs - Personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)
    *   必要なスコープ: `repo` (すべてのプライベートリポジトリへのアクセスを含む)

### 2.5 対象GitHubリポジトリ
*   **テスト用リポジトリ**: テスト目的で、このActivityによる操作を許可するGitHubリポジトリを用意してください。本Activityはリポジトリのブランチやファイルを変更するため、本番環境のリポジトリではなく、**テスト専用のリポジトリの使用を強く推奨します。**

## 3. GitHub Pull Request Activity 概要

`create_pull_request` Activityは、指定された入力パラメータに基づいて、GitHub上で一連の操作を実行し、プルリクエストを作成することを目的としたTemporal Activityです。

### 3.1 提供される機能
*   GitHubリポジトリのクローンまたは最新状態への更新。
*   フィーチャーブランチの作成およびチェックアウト。
*   指定されたファイルパスへのコンテンツ書き込み（親ディレクトリの自動作成を含む）。
*   変更内容のコミット。
*   フィーチャーブランチへの強制プッシュ。
*   プルリクエストの作成。既存の同ブランチからのPRがあれば、そのURLを返すことで冪等性を保ちます。

### 3.2 入力パラメータ
`create_pull_request` Activityは、以下のキーを持つ辞書をパラメータとして受け取ります。

| パラメータ名       | 型     | 説明                                                              | 例                                   |
| :----------------- | :----- | :---------------------------------------------------------------- | :----------------------------------- |
| `repository`       | `str`  | PRを作成する対象のGitHubリポジトリ名（`owner/repo`形式）。     | `"octocat/Spoon-Knife"`              |
| `base_branch`      | `str`  | PRのマージ先となるベースブランチ名。                            | `"main"`                             |
| `feature_branch`   | `str`  | 変更をコミットしてプッシュするフィーチャーブランチ名。       | `"feature/temporal-test-branch"`     |
| `commit_message`   | `str`  | GitHubにプッシュするコミットのメッセージ。                    | `"feat: Add test file via Temporal"` |
| `pr_title`         | `str`  | 作成するプルリクエストのタイトル。                             | `"Temporal Test PR"`                 |
| `pr_body`          | `str`  | 作成するプルリクエストの本文。                                | `"This PR adds a test file."`        |
| `file_path`        | `str`  | リポジトリ内でコンテンツを書き込むファイルのパス（ルートからの相対）。 | `"docs/test_sop.md"`                 |
| `file_content`     | `str`  | 指定されたファイルに書き込む内容。                            | `"## Test SOP\nThis is a test content."` |

### 3.3 期待される出力
Activityが正常に完了すると、作成または更新されたプルリクエストのURLを含む辞書を返します。

```json
{"pr_url": "https://github.com/owner/repo/pull/N"}
```

### 3.4 内部で利用されるCLIツール
本Activityは、以下のCLIツールを内部で利用しています。
*   **`git CLI`**:
    *   リポジトリのクローン、フェッチ、リモートURL設定。
    *   ブランチのチェックアウト、コミット、プッシュ。
*   **`gh CLI`**:
    *   既存のプルリクエストの確認。
    *   新しいプルリクエストの作成。

これらのツールを使用することで、複雑なGitHub APIを直接操作することなく、GitHubの機能を活用し、堅牢な操作を実現しています。

## 4. 環境準備

SOPを実行する前に、必要なCLIツールのインストール、認証設定、およびTemporal Workerの起動方法について説明します。

### 4.1 Git CLIのインストール
お使いのOSに合わせてGit CLIをインストールしてください。

*   **Debian/Ubuntu**:
    ```bash
    sudo apt update
    sudo apt install git
    ```
*   **macOS (Homebrew)**:
    ```bash
    brew install git
    ```
*   **Windows**: [Git for Windows](https://gitforwindows.org/) をダウンロードしてインストールしてください。

インストール後、以下のコマンドでバージョンを確認し、正しくインストールされていることを確認してください。
```bash
git --version
```

### 4.2 GitHub CLI (`gh CLI`) のインストールと認証
お使いのOSに合わせて`gh CLI`をインストールしてください。

*   **Debian/Ubuntu**:
    ```bash
    type -p curl >/dev/null || (sudo apt update && sudo apt install curl -y)
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && sudo apt update \
    && sudo apt install gh -y
    ```
*   **macOS (Homebrew)**:
    ```bash
    brew install gh
    ```
*   **Windows**: [GitHub CLI 公式ウェブサイト](https://cli.github.com/) からインストーラーをダウンロードするか、[scoop](https://scoop.sh/) や [winget](https://docs.microsoft.com/ja-jp/windows/package-manager/winget/) を利用してください。

インストール後、以下のコマンドでバージョンを確認し、正しくインストールされていることを確認してください。
```bash
gh --version
```

次に、`gh CLI`を認証します。
```bash
gh auth login
```
プロンプトに従って、WebブラウザまたはPersonal Access Token（PAT）を使用して認証を完了してください。**この際、求められるスコープの中から`repo`スコープを選択し、付与するようにしてください。** `GITHUB_TOKEN`環境変数はGit操作で使用されますが、`gh CLI`は独自の認証を必要とします。

認証後、`gh auth status`コマンドで認証状態を確認できます。

### 4.3 `GITHUB_TOKEN` 環境変数の設定
GitHub Personal Access Token（PAT）を`GITHUB_TOKEN`という名前の環境変数に設定します。このPATは、**Gitの認証（リポジトリのクローンやプッシュ時、Git URLに埋め込まれて使用されます）** に使用されます。

```bash
export GITHUB_TOKEN="YOUR_PERSONAL_ACCESS_TOKEN"
```
**注意**: `YOUR_PERSONAL_ACCESS_TOKEN` をあなたの実際のPATに置き換えてください。このトークンは機密情報であるため、漏洩しないように注意してください。永続化するためには、`.bashrc`、`.zshrc`、または同等のシェル設定ファイルに追加することを推奨します。

### 4.4 Temporal Workerの起動
提供されたPythonコード（`GitHubActivity`クラス）を含むファイルをTemporal Workerがアクセスできる場所に配置し、Workerを起動します。

**例: Activityコードの配置とWorkerの起動**
1.  Activityクラスを `activities/github_activity.py` のようなファイルに保存します。
    ```python
    # activities/github_activity.py
    import asyncio
    import os
    import tempfile
    from pathlib import Path
    import subprocess
    from temporalio import activity
    # ... GitHubActivity クラスの実装が続く ...

    class GitHubActivity:
        # ... メソッド群 ...
        @activity.defn
        async def create_pull_request(self, params: dict) -> dict:
            # ... 実装 ...
            pass
    ```
2.  Workerスクリプト (`worker.py`) を作成し、Activityをインポートして登録します。
    ```python
    # worker.py
    import asyncio
    from temporalio.worker import Worker
    from activities.github_activity import GitHubActivity # Activityクラスを含むファイルをインポート

    async def main():
        worker = Worker(
            "your-task-queue", # ワークフローから指定されるタスクキュー名
            activities=[GitHubActivity().create_pull_request],
        )
        activity.logger.info(f"Starting worker for task queue 'your-task-queue'...")
        await worker.run()

    if __name__ == "__main__":
        asyncio.run(main())
    ```
3.  Workerを起動します。
    ```bash
    python worker.py
    ```
    これにより、`GitHubActivity`の`create_pull_request` Activityが`your-task-queue`で利用可能になります。

## 5. SOP実行手順（Temporal Workflowからの呼び出し）

Temporal Workflowから`create_pull_request` Activityを呼び出す具体的な手順と、必要なパラメータの詳細を説明します。

### 5.1 Workflow定義の例
以下は、`create_pull_request` Activityを呼び出すTemporal WorkflowのPythonコード例です。

```python
# workflow.py
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

# Activity定義をインポート (worker.pyでActivityクラスを登録するのと同様に、ワークフローからも参照できるようにする)
from activities.github_activity import GitHubActivity

@workflow.defn
class GitHubPrWorkflow:
    @workflow.run
    async def run(self, params: dict) -> dict:
        # Activity呼び出しオプションの設定
        # Activityの実行タイムアウトを十分に確保することが重要。
        # Git操作やGitHub API呼び出しはネットワーク状況によって時間がかかる可能性があるため。
        result = await workflow.execute_activity(
            GitHubActivity().create_pull_request, # Activityのインスタンスとメソッドを指定
            params,
            start_to_close_timeout=timedelta(minutes=5), # アクティビティの実行時間制限
            retry_policy=RetryPolicy(maximum_attempts=3), # 失敗時のリトライポリシー
        )
        return result

# 実行クライアントの例（別ファイル、または同じファイルの__main__ブロック内）
import asyncio
from temporalio.client import Client
from temporalio import workflow # workflow.now() を使うためにインポート

async def execute():
    client = await Client.connect("localhost:7233") # Temporal Serverのアドレス
    
    # Activityに渡すパラメータ
    # workflow.now() は Temporal Workflow の時間であり、Activity が実行されるリアルタイムの時間とは異なる場合があります。
    workflow_params = {
        "repository": "YOUR_GITHUB_USER/YOUR_TEST_REPO", # 例: "myuser/my-test-repo"
        "base_branch": "main",
        "feature_branch": "feature/temporal-auto-pr-test",
        "commit_message": "feat: Add new Temporal test file",
        "pr_title": "Temporal Auto PR Test: New File",
        "pr_body": "This PR was automatically generated by a Temporal Workflow for testing purposes. It adds a new test file.",
        "file_path": "test_files/temporal_test_file.txt",
        "file_content": f"Hello from Temporal Workflow! This file was created at {workflow.now()}."
    }

    # Workflowの実行
    handle = await client.execute_workflow(
        GitHubPrWorkflow.run,
        workflow_params,
        id="github-pr-workflow-test",
        task_queue="your-task-queue",
    )

    print(f"Workflow ID: {handle.id}")
    print(f"Workflow Result: {await handle.result()}")

if __name__ == "__main__":
    asyncio.run(execute())
```

### 5.2 パラメータの詳細と指定例
`workflow_params`辞書内の各パラメータについて、その役割と具体的な指定例を再度確認します。

*   **`repository`**: `YOUR_GITHUB_USER/YOUR_TEST_REPO`
    *   例: `"myuser/my-test-repo"`
    *   PRを作成する対象のリポジトリです。`owner/repository_name`の形式で指定します。このリポジトリは事前に作成しておく必要があります。
*   **`base_branch`**: `main`
    *   例: `"main"`
    *   PRのマージ先となるブランチです。通常は`main`や`master`を指定します。
*   **`feature_branch`**: `feature/temporal-auto-pr-test`
    *   例: `"feature/my-new-feature-branch"`
    *   変更をコミットし、プッシュするブランチです。このブランチが存在しない場合は作成され、存在する場合は強制的に最新の変更がプッシュされます。テスト用途ではユニークなブランチ名を使用することを推奨します。
*   **`commit_message`**: `feat: Add new Temporal test file`
    *   例: `"docs: Update documentation for SOP"`
    *   Gitコミットに使用されるメッセージです。
*   **`pr_title`**: `Temporal Auto PR Test: New File`
    *   例: `"feat: Add Temporal Activity SOP"`
    *   作成されるプルリクエストのタイトルです。
*   **`pr_body`**: `This PR was automatically generated by a Temporal Workflow for testing purposes. It adds a new test file.`
    *   例: `"This pull request updates the documentation based on the new Temporal Activity for GitHub PR creation."`
    *   作成されるプルリクエストの本文です。Markdown形式も利用可能です。
*   **`file_path`**: `test_files/temporal_test_file.txt`
    *   例: `"src/activities/new_feature_config.json"`
    *   リポジトリのルートディレクトリからの相対パスで、コンテンツを書き込むファイルを指定します。必要に応じて親ディレクトリが自動的に作成されます。
*   **`file_content`**: `f"Hello from Temporal Workflow! This file was created at {workflow.now()}."`
    *   例: `"{\"version\": \"1.0\", \"status\": \"active\"}"`
    *   指定された`file_path`に書き込まれる文字列コンテンツです。

### 5.3 Workflowの実行
`execute()`関数を実行してWorkflowを開始します。
```bash
python workflow.py # 上記のexecute()関数を呼び出すスクリプト
```
成功すると、Workflow IDと、`pr_url`を含む結果が出力されます。

## 6. ActivityによるGitHub操作詳細

`create_pull_request` Activityが内部で実行する一連のGitHub操作について、ソースコードのプライベートヘルパーメソッドと対応させながら詳細に解説します。

### 6.1 `_clone_or_update_repo` (リポジトリのクローン/更新)
*   **意図**: 対象のリポジトリがローカルに存在しない場合はクローンし、存在する場合は最新の状態に更新します。`GITHUB_TOKEN`環境変数に設定されたPATをURLに埋め込むことで、認証情報を明示的に渡します。
*   **内部コマンド**:
    *   `git -C <repo_dir> remote set-url origin https://<GITHUB_TOKEN>@github.com/<repository>.git`: リモートのURLを更新し、PATを埋め込みます。これにより、以降の`git fetch`/`git push`で認証が不要になります。
    *   `git -C <repo_dir> fetch --all`: リモートの全ブランチ情報を取得し、ローカルを最新化します。
    *   `git clone https://<GITHUB_TOKEN>@github.com/<repository>.git <repo_dir>`: リポジトリがローカルに存在しない場合にクローンします。

### 6.2 `_checkout_branch` (フィーチャーブランチのチェックアウト)
*   **意図**: 指定されたフィーチャーブランチが存在しない場合は作成し、存在する場合はそのブランチに切り替えます。`-B`オプションを使用することで、既存のブランチを上書きする形で作成またはリセットされます。これはテスト用途において、常にクリーンな状態から操作を開始するのに役立ちます。
*   **内部コマンド**:
    *   `git -C <repo_dir> checkout -B <branch>`: `<branch>`が存在しなければ作成しチェックアウト、存在すれば現在のHEADを`<branch>`にリセットしチェックアウトします。

### 6.3 `_write_content` (ファイルコンテンツの書き込み)
*   **意図**: 指定されたリポジトリ内のパスに、提供されたコンテンツを書き込みます。ファイルの親ディレクトリが存在しない場合は、自動的に作成されます。
*   **内部処理**: Pythonの`pathlib.Path`オブジェクトを利用してファイルパスを扱い、`mkdir(parents=True, exist_ok=True)`で安全にディレクトリを作成し、`write_text(content, encoding="utf-8")`でコンテンツを書き込みます。

### 6.4 `_commit_and_push` (コミットと強制プッシュ)
*   **意図**: 作業ディレクトリ内のすべての変更をステージングし、コミットし、そして指定されたフィーチャーブランチに強制プッシュします。差分がない場合はコミットをスキップし、プッシュのみ実行することで冪等性を保証します。`--force`オプションは、ローカルブランチの履歴がリモートと異なる場合でもプッシュを強制し、ブランチ履歴を上書きします。これはテスト用途でブランチの状態を確実に制御するために使用されます。
*   **内部コマンド**:
    *   `git -C <repo_dir> add -A`: すべての変更（追加、変更、削除）をステージングします。
    *   `git -C <repo_dir> diff --cached --quiet`: ステージングされた変更があるかを確認します。差分がない場合、このコマンドは成功（returncode=0）します。
    *   `git -C <repo_dir> config user.email "temporal-worker@local"`
    *   `git -C <repo_dir> config user.name "Temporal Worker"`: コミットの作成者情報を設定します。
    *   `git -C <repo_dir> commit -m <message>`: ステージングされた変更をコミットします。
    *   `git -C <repo_dir> push --force origin <branch>`: 指定されたブランチをリモートに強制プッシュします。

### 6.5 `_submit_pr` (プルリクエストの作成/更新)
*   **意図**: `gh CLI`を使用してプルリクエストを作成します。`gh CLI`は、同じブランチからの既存のPRを検出し、新しいPRを作成する代わりにそのPRのURLを返すことで、冪等性を確保します。
*   **内部コマンド**:
    *   `gh pr list --head <head> --repo <repository> --json url --jq '.[0].url'`: 指定されたヘッドブランチからの既存PRを検索し、そのURLを抽出します。
    *   `gh pr create --repo <repository> --base <base> --head <head> --title <title> --body <body>`: 新しいプルリクエストを作成します。

## 7. 実行結果の確認

Activity実行後、返された情報（プルリクエストURL）の確認方法と、GitHub上で実際にプルリクエストが作成・更新されているかを確認する手順を説明します。

### 7.1 Temporal Workflow実行ログの確認
Temporal Workflowが正常に完了すると、`execute()`関数（クライアントコード）の出力に、Activityが返した`pr_url`が含まれているはずです。

**成功時の出力例**:
```
Workflow ID: github-pr-workflow-test
Workflow Result: {'pr_url': 'https://github.com/myuser/my-test-repo/pull/123'}
```
この`pr_url`をコピーしてブラウザで開くことで、直接プルリクエストにアクセスできます。

### 7.2 GitHub UIでの確認
`pr_url`からプルリクエストに直接アクセスする以外に、GitHub UIで以下の点を確認します。

1.  **対象リポジトリへのアクセス**: ブラウザで`https://github.com/YOUR_GITHUB_USER/YOUR_TEST_REPO`にアクセスします。
2.  **ブランチの確認**:
    *   リポジトリのブランチ一覧で、`feature/temporal-auto-pr-test`のような`feature_branch`で指定したブランチが作成されていることを確認します。
    *   そのブランチの最新コミットが、`commit_message`で指定したメッセージと一致することを確認します。
3.  **ファイル変更の確認**:
    *   `feature_branch`に切り替えて、`file_path`で指定したファイル（例: `test_files/temporal_test_file.txt`）が作成されているか、または更新されているかを確認します。
    *   ファイルのコンテンツが`file_content`で指定した内容と一致することを確認します。
4.  **プルリクエストの確認**:
    *   リポジトリの「Pull requests」タブに移動します。
    *   `pr_title`で指定したタイトルのプルリクエストが存在することを確認します。
    *   プルリクエストを開き、その本文が`pr_body`で指定した内容と一致することを確認します。
    *   プルリクエストの「Files changed」タブで、`file_path`で指定したファイルの変更が期待通りであるかを確認します。
    *   PRのステータス（例: Open）を確認します。

これらの確認がすべて期待通りであれば、ActivityによるGitHub操作は正常に機能していると判断できます。

## 8. エラーハンドリングとトラブルシューティング

Activity実行中に発生しうる一般的なエラーとその原因、および対処方法について解説します。

### 8.1 `EnvironmentError: GITHUB_TOKEN が設定されていません。`
*   **原因**: 環境変数`GITHUB_TOKEN`が設定されていないか、Workerプロセスから参照できない状態です。
*   **対処法**:
    1.  `export GITHUB_TOKEN="YOUR_PAT"`コマンドを実行して、`GITHUB_TOKEN`を現在のシェルセッションに設定します。
    2.  Workerを起動するシェルで`echo $GITHUB_TOKEN`を実行し、値が正しく表示されることを確認します。
    3.  `GITHUB_TOKEN`が永続的に設定されるよう、`.bashrc`や`.zshrc`などのシェル設定ファイルに追記します。
    4.  ワーカーサービスとして起動している場合は、サービス設定ファイルで環境変数がロードされるように設定します。

### 8.2 `subprocess.CalledProcessError`
*   **原因**: 内部で実行される`git CLI`または`gh CLI`コマンドが失敗しました。これは様々な理由で発生する可能性があります。
    *   `git CLI`または`gh CLI`がインストールされていない、またはパスが通っていない。
    *   GitHub Personal Access Token（PAT）の権限不足（例: `repo`スコープがない）。
    *   リポジトリ名、ブランチ名、ファイルパスなどに誤りがある。
    *   `gh CLI`の認証が期限切れ、または正しく行われていない。
    *   ネットワークの問題によりGitHubへの接続ができない。
*   **対処法**:
    1.  **Activityログの確認**: Temporal UIまたはWorkerのログで、`subprocess.CalledProcessError`の詳細（`stdout`と`stderr`）を確認します。これにより、どのコマンドが失敗し、どのようなエラーメッセージが出力されたかが分かります。
        *   例: `Command '['git', '-C', ... 'push', '--force', 'origin', '...' ]' returned non-zero exit status 128: stderr: 'remote: Permission to ... denied.'` のようなメッセージは権限不足を示唆します。
    2.  **CLIコマンドの手動実行**: エラーが発生した`git`または`gh`コマンドを、Workerが実行されている環境と同じユーザーで手動で実行し、問題を再現できるか確認します。
        *   例: `gh auth status`, `git ls-remote https://github.com/owner/repo.git`, `git push --force origin <branch>`
    3.  **PATの権限確認**: GitHubのPAT設定ページで、使用しているトークンに`repo`スコープが付与されていることを確認します。必要であれば再生成します。
    4.  **`gh CLI`認証の確認**: `gh auth status`コマンドを実行し、`gh CLI`がGitHubに正常に認証されていることを確認します。必要であれば`gh auth login`で再認証します。
    5.  **入力パラメータの確認**: Workflowに渡した`params`辞書内の`repository`, `base_branch`, `feature_branch`などの値が正しいことを再確認します。

### 8.3 その他の一般的なデバッグ方法
*   **Activityロギングの活用**: Activity内で`activity.logger.info()`や`activity.logger.debug()`を使用して、詳細なログを出力します。特に`subprocess.run`の`stdout`と`stderr`の内容をログに出力することで、デバッグ情報が増えます。
    ```python
    # _clone_or_update_repo メソッド内で (例)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "fetch", "--all"],
            check=True, capture_output=True,
        )
        activity.logger.info(f"git fetch stdout: {result.stdout.decode()}")
        activity.logger.warning(f"git fetch stderr: {result.stderr.decode()}") # stderr は通常エラーだが、警告として出すことも
    except subprocess.CalledProcessError as e:
        activity.logger.error(f"git fetch failed: {e.stderr.decode()}")
        raise
    ```
*   **ローカルでの単体テスト**: ActivityのコードをTemporal環境なしで、直接Pythonスクリプトとして実行し、GitHub操作の部分だけを切り出してテストします。

## 9. 注意事項とベストプラクティス

このActivityを実戦疎通テスト以外の目的で使用する場合の考慮事項、ブランチ戦略、および一時ファイルの管理などに関する注意事項を提供します。

### 9.1 テスト環境での利用を強く推奨
*   本Activityは`git push --force`（強制プッシュ）を使用しており、ブランチの履歴を破壊する可能性があります。本番環境や共有リポジトリでの無差別な使用はデータ損失や混乱を招く恐れがあります。**必ずテスト専用のリポジトリとブランチで使用してください。**
*   ActivityはローカルリポジトリをOSの一時ディレクトリ内に作成します。これは一時的な作業領域として扱われるため、永続的なリポジトリ管理には適しません。

### 9.2 ブランチ戦略
*   テストにおいては、`feature/temporal-test-YYYYMMDD-HHMMSS`のように、タイムスタンプやユニークな識別子を含むブランチ名を`feature_branch`として使用することを推奨します。これにより、テスト実行ごとに新しいブランチが作成され、他のテスト実行や手動操作との競合を避けることができます。
*   テスト完了後には、作成されたフィーチャーブランチとプルリクエストをクリーンアップする別途のActivityや手動作業を検討してください。

### 9.3 一時ファイルの管理
*   Activityは、クローンしたリポジトリをOSの一時ディレクトリ内（例: Linux/macOS では `/tmp/temporal_github`）に保存します。
*   これらのディレクトリはOSや設定によっては自動的に削除されることがありますが、そうでない場合はディスクスペースを消費する可能性があります。Workerの再起動時や定期的なクリーンアップスクリプトの実行を検討してください。
    *   **手動クリーンアップの例 (Linux/macOS)**:
        ```bash
        rm -rf /tmp/temporal_github
        ```
    *   **注意**: このコマンドは慎重に実行し、他の重要なデータが誤って削除されないように十分注意してください。

### 9.4 権限の最小化
*   `GITHUB_TOKEN`には、必要な最小限の権限（スコープ）のみを付与してください。本Activityでは`repo`スコープがあれば動作しますが、より細かい権限設定が可能な場合は検討してください。セキュリティリスクを最小限に抑えることが重要です。

### 9.5 冪等性の考慮
*   本Activityは、既存のプルリクエストを検出する (`_submit_pr` メソッド) ことや、差分がない場合のコミットをスキップする (`_commit_and_push` メソッド) ことにより、ある程度の冪等性を確保しています。Activityが複数回実行されても、同じ入力に対して同じ結果（同じPRが作成または更新され、同じURLが返される）が得られるように設計されています。

### 9.6 `gh CLI`のバージョン互換性
*   `gh CLI`のバージョンアップにより、コマンドオプションや出力形式が変更される可能性があります。将来的に本Activityが期待通りに動作しない場合は、`gh CLI`のバージョンと公式ドキュメントを確認し、必要に応じてコードを修正してください。

### 9.7 コミットユーザー情報
*   Activityはコミット時に`user.email`と`user.name`を`temporal-worker@local`と`Temporal Worker`に設定しています。これを実際のユーザー名やボット名に変更したい場合は、`_commit_and_push`メソッド内の`git config`コマンドを修正してください。
```