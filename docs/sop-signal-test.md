## ドキュメント化対象
Temporal Workflow `create_pull_request` Activity 疎通テスト用SOP (Human-in-the-Loop 前提検証)

---

## 1. はじめに

この標準作業手順書（SOP）は、Temporal Workflowの`GitHubActivity`クラス内に定義された`create_pull_request` Activityの疎通テストに関する詳細な手順を提供します。このActivityは、指定されたGitHubリポジトリに対してファイルを作成し、コミット、プッシュを行い、最終的にPull Request（PR）を作成する一連の操作を自動化します。

### 1.1. 目的

本SOPの主な目的は、`create_pull_request` Activityが期待通りに動作し、GitHub上でPull Requestを正確に作成できることを検証することです。これにより、後続のTemporal Human-in-the-Loop検証フローにおける「approve_pr Signal」を用いたPR承認プロセスが円滑に進むための**前提条件**が満たされていることを確認します。このテストが成功することで、Human-in-the-Loopワークフローの最初の自動化ステップが確実に機能することが保証されます。

### 1.2. スコープ

本SOPのスコープは以下の操作を含みます。

*   Temporal Worker環境の準備。
*   必要なCLIツール（`git`, `gh`）および認証情報（GitHub Personal Access Token）の設定。
*   `create_pull_request` Activityへの入力パラメータの準備。
*   Temporal WorkflowからのActivity呼び出しおよび実行の監視。
*   GitHub上でのPull Request作成結果の確認。
*   一般的な問題に対するトラブルシューティング。

### 1.3. Human-in-the-Loop 検証フローにおける位置付け

`create_pull_request` Activityは、Temporal Human-in-the-Loop検証フローにおいて、自動化されたコード変更提案の最初のステップを担います。Workflowは本Activityを通じて、人間のレビューが必要な変更をPull RequestとしてGitHub上に提示します。その後、人間がそのPull Requestをレビューし、承認の可否を`approve_pr Signal`を通じてWorkflowに通知することで、次のステップ（例: PRのマージ、デプロイ）に進みます。したがって、本Activityが正しく動作することは、Human-in-the-Loopフロー全体の健全性にとって不可欠です。本SOPは、この重要な最初のステップの機能検証に特化しています。

---

### 重要な注意事項

*   **本番環境でのテスト回避**: 本SOPに記載された手順は、テスト専用のGitHubリポジトリおよびTemporal環境で実行してください。本番環境や機密情報を含むリポジトリでは絶対に実行しないでください。
*   **Personal Access Token (PAT) の厳重な管理**: GitHub Personal Access Token (PAT) は、GitHubアカウントへのアクセス権限を持つ非常に機密性の高い情報です。PATが漏洩すると、リポジリへの不正アクセスやデータの改ざんにつながる可能性があります。
    *   テスト専用のPATを使用し、不要になったら速やかにGitHubから削除してください。
    *   PATのスコープは、必要最小限の権限に設定してください（ただし、本SOPでは便宜上`repo`スコープを推奨しています。詳細は「3.3. GitHub Personal Access Token」を参照）。
    *   PATをコードや設定ファイルに直接ハードコードしないでください。環境変数やシークレット管理システムを利用してください。
*   **テストリソースの準備**: GitHubリポジトリ、Temporalタスクキューなど、テストで使用するすべてのリソースは、本SOP専用に準備し、既存の運用環境に影響を与えないようにしてください。

---

## 2. 前提条件と準備

本SOPに記載された手順を実行する前に、以下の前提条件が満たされていること、および準備作業が完了していることを確認してください。

### 2.1. 適切なPython環境

*   **Pythonバージョン**: Python 3.8以降がインストールされていること。
*   **依存ライブラリ**: Temporal SDK for Python (`temporalio`) がインストールされていること。
    ```bash
    pip install temporalio
    ```

### 2.2. Temporal Workerのセットアップ

`create_pull_request` Activityを実行するTemporal Workerは、以下の要件を満たしている必要があります。

*   **Workerの起動**: テスト対象のActivityを登録したTemporal Workerが、適切なタスクキューで起動していること。
*   **Activity登録**: `GitHubActivity`クラスがWorkerに登録されていること。
*   **実行環境**: Workerが動作する環境に、GitHub CLI (`gh`) とGit CLI (`git`) がインストールされており、PATHが通っていること。また、GitHubへのアクセスに必要なネットワーク設定が完了していること。

### 2.3. テスト用GitHubリポジトリの準備

*   **リポジトリの作成**: GitHub上にテスト用のリポジトリを準備してください。このリポジリは公開・非公開のどちらでも構いませんが、Workerがアクセスできる必要があります。
    *   例: `your-github-username/your-test-repo`
*   **基本ブランチの確認**: PRの`base_branch`として指定するブランチ（例: `main`または`master`）がリポジトリ内に存在することを確認してください。
*   **権限**: 後述の`GITHUB_TOKEN`を発行するGitHubユーザー（または組織）が、このテスト用リポジトリに対する書き込み権限（Push権限）を持っている必要があります。

### 2.4. 実行環境へのネットワークアクセス

*   Temporal Cluster (通常は `localhost:7233` または指定されたホスト/ポート) へのアクセス。
*   GitHub API (api.github.com) へのHTTPS (ポート443) アクセス。

## 3. 必要なツールと認証設定

`create_pull_request` Activityは、内部で`git CLI`と`gh CLI`（GitHub CLI）を利用してGitHubとの連携を行います。これらのツールが正しくインストールされ、認証設定が完了している必要があります。

### 3.1. `git CLI` のインストールと設定

`git`はバージョン管理の基本ツールです。多くの開発環境にはプリインストールされていますが、そうでない場合はお使いのOSのパッケージマネージャーを使用してインストールしてください。

*   **インストール確認**: ターミナルで以下のコマンドを実行し、バージョンが表示されることを確認します。
    ```bash
    git --version
    ```
    (例: `git version 2.37.1`)
*   **ユーザー情報の設定**: `create_pull_request` Activityは内部でコミットユーザー情報を設定しますが、システム全体の`git`設定が正しいことも確認しておくと良いでしょう。
    ```bash
    git config --global user.name "Your Name"
    git config --global user.email "your.email@example.com"
    ```

### 3.2. `gh CLI` のインストールと設定

`gh CLI`はGitHub公式のコマンドラインインターフェースであり、`create_pull_request` ActivityでPull Requestの作成に使用されます。

*   **インストール**: 公式ドキュメントを参照し、お使いのOSに応じた方法でインストールしてください。
    *   GitHub CLI インストールガイド: [https://github.com/cli/cli#installation](https://github.com/cli/cli#installation)
*   **認証設定**: インストール後、以下のコマンドでGitHubアカウントへの認証を行います。
    ```bash
    gh auth login
    ```
    プロンプトに従って、GitHub EnterpriseまたはGitHub.comを選択し、認証トークン発行サイトにアクセスしてPersonal Access Token（後述）を入力するか、ブラウザでの認証フローを完了させてください。
*   **認証確認**: 以下のコマンドで認証状態を確認します。
    ```bash
    gh auth status
    ```
    (例: `Logged in to github.com as <your-username> (<your-github-token-scope>)`)

### 3.3. GitHub Personal Access Token (`GITHUB_TOKEN`) の取得と環境変数への設定

`create_pull_request` Activityは、リポジリのクローンやプッシュのために`GITHUB_TOKEN`環境変数に設定されたPersonal Access Token（PAT）を使用します。

*   **トークンの取得方法**:
    1.  GitHubにログインし、**Settings** にアクセスします。
    2.  左側のナビゲーションメニューで **Developer settings** をクリックします。
    3.  **Personal access tokens** セクションで **Tokens (classic)** をクリックします。
    4.  **Generate new token** ボタンをクリックし、**Generate new token (classic)** を選択します。
    5.  **Note**: トークンの目的を識別しやすい名前（例: "Temporal PR Activity Test"）を入力します。
    6.  **Expiration**: 有効期限を設定します（テスト用途であれば短期間で十分です）。
    7.  **Select scopes**: 以下のスコープを選択します。
        *   `repo` (すべてのリポジリへのアクセス権限)
        *   `workflow` (GitHub Actions workflowのアクセス権限、必須ではないが推奨)
        *   **【重要】最低限、テスト対象のリポジリに対して書き込み権限を与えるスコープ（例: `public_repo`または`repo`全体）が必要です。`repo`スコープを選択することを強く推奨しますが、このスコープは**すべてのリポジリ**へのフルアクセス権限を与えるため、セキュリティリスクが高いことを理解し、テスト用途に限定してください。より厳密な権限管理が必要な場合は、[Fine-grained Personal Access Tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token) の利用を検討してください。
    8.  **Generate token** ボタンをクリックします。
    9.  生成されたトークンは一度しか表示されないため、**必ず安全な場所に控えてください**。

*   **環境変数への設定**:
    Workerが動作する環境で、取得したPATを`GITHUB_TOKEN`という環境変数に設定します。

    *   **Linux/macOS (bash/zsh)**:
        ```bash
        export GITHUB_TOKEN="ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        ```
        一時的な設定です。永続化するには、`.bashrc`, `.zshrc`, またはシステム全体の`/etc/environment`などに追記します。
    *   **Windows (PowerShell)**:
        ```powershell
        $env:GITHUB_TOKEN="ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        ```
        一時的な設定です。永続化するには、システム環境変数として設定します。
    *   **Windows (CMD)**:
        ```cmd
        set GITHUB_TOKEN=ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
        ```
        一時的な設定です。永続化するには、システム環境変数として設定します。
    Workerをサービス（例: Systemdサービス）として実行している場合は、サービス起動スクリプトやUnitファイル内で環境変数を設定するか、Kubernetesなどのコンテナオーケストレーション環境であればPodの環境変数（ConfigMapやSecretを使用）として安全に設定してください。

*   **設定の確認**:
    ターミナルで以下のコマンドを実行し、トークンが正しく設定されていることを確認します（実際のトークン値ではなく、先頭数文字と末尾数文字で確認するなど、セキュリティに配慮してください）。
    ```bash
    echo $GITHUB_TOKEN # Linux/macOS
    echo $env:GITHUB_TOKEN # PowerShell
    ```

## 4. GitHub PR作成Activityの概要

`create_pull_request` Activityは、Temporal Workflowから呼び出され、GitHubリポジリに対する一連のGit操作とPull Request作成を自動的に実行します。これにより、コードの変更提案がレビュー可能な状態としてGitHub上に提示されます。

### 4.1. 機能と役割

本Activityは、SOPや修正コードなどのコンテンツをGitHubリポジリにコミットし、その変更を含むPull Requestを開通させる役割を担います。これにより、Human-in-the-Loopの承認フローの起点となる変更をプログラムから自動で作成できます。

### 4.2. Activityが実行する一連の操作

1.  **リポジリのクローンまたは更新**:
    *   指定されたリポジリがWorkerの一時ディレクトリ（`tempfile.gettempdir() / "temporal_github"`）に存在しない場合、GitHubからクローンします。
    *   既に存在する場合、`origin`リモートのURLを更新し、すべてのリモートブランチをフェッチして最新の状態にリセットします。
    *   **注**: この一時ディレクトリはWorkerプロセスが動作している間にのみ存在し、Workerの再起動や異なるWorkerインスタンスでリトライされた場合には再クローンされます。これはActivityの冪等性確保に貢献しますが、ディスク容量には注意が必要です。
2.  **フィーチャブランチのチェックアウト**:
    *   指定された`feature_branch`名で新しいブランチをチェックアウトします。
    *   同名のブランチが既に存在する場合、そのブランチを強制的にリセット（上書き）します。
3.  **ファイルの書き込み**:
    *   指定された`file_path`に、提供された`file_content`を書き込みます。
    *   必要に応じて、親ディレクトリを自動的に作成します。
4.  **変更のコミットとプッシュ**:
    *   リポジリ内のすべての変更をステージング (`git add -A`) します。
    *   変更がある場合、指定された`commit_message`でコミットします。コミットユーザーは`Temporal Worker <temporal-worker@local>`として設定されます。
    *   `feature_branch`を`origin`に対して**強制プッシュ** (`git push --force`) します。これにより、以前の履歴が上書きされる可能性があるため注意が必要です。
5.  **Pull Requestの作成**:
    *   `gh CLI`を使用してPull Requestを作成します。
    *   同じ`head`ブランチを持つPRが既に存在する場合、`gh pr create`コマンドは新しいPRを作成せず、既存のPRのURLを返します（冪等性）。`gh CLI`は既存のPRを自動的に検出し、その情報を使用するため、事前に`gh pr list`などでPRの存在を確認する追加のステップは不要です。
    *   `base_branch`、`feature_branch`、`pr_title`、`pr_body`などの情報がPRに設定されます。

### 4.3. 期待される出力

Activityは、成功すると作成または既存のPull RequestのURLを含む辞書を返します。
```json
{
  "pr_url": "https://github.com/owner/repo/pull/N"
}
```

## 5. Activity入力パラメータの詳細

`create_pull_request` Activityは、単一の辞書型パラメータ`params`を受け取ります。この辞書には、PR作成に必要なすべての情報が含まれます。以下に各キーの詳細、型、および設定例を示します。

| キー             | 型     | 必須 | 説明                                                                                       | 設定例                                           |
| :--------------- | :----- | :--- | :----------------------------------------------------------------------------------------- | :----------------------------------------------- |
| `repository`     | `str`  | はい | GitHubリポジリのフルネーム (`owner/repo`)。                                              | `"my-github-org/my-app-repo"`                    |
| `base_branch`    | `str`  | はい | PRのマージ先となるブランチ名。通常は `main` や `master`。                                | `"main"`                                         |
| `feature_branch` | `str`  | はい | PRのHEADブランチとなるフィーチャブランチ名。Activityにより作成または上書きされます。     | `"feat/add-new-sop-doc"`                         |
| `commit_message` | `str`  | はい | コミットメッセージ。`git commit`時に使用されます。                                       | `"docs: Add initial SOP"`                        |
| `pr_title`       | `str`  | はい | Pull Requestのタイトル。                                                                 | `"SOP Update: New Policy Document"`              |
| `pr_body`        | `str`  | はい | Pull Requestの本文。Markdown形式で記述可能です。                                         | `"This PR introduces a new policy for review."` |
| `file_path`      | `str`  | はい | リポジリのルートからの相対パスで指定するファイル名。`file_content`が書き込まれます。   | `"docs/policy/new_policy.md"`                    |
| `file_content`   | `str`  | はい | `file_path`で指定されたファイルに書き込む内容。                                          | `"# New Policy\n\n1. Purpose..."`                |

### 5.1. `params` 辞書の設定例

以下は、Temporal Workflowから`create_pull_request` Activityを呼び出す際に使用する`params`辞書の具体的な例です。

```python
pr_params = {
    "repository": "your-github-username/your-test-repo",  # ご自身のGitHubユーザー名とリポジリ名に置き換えてください
    "base_branch": "main",
    "feature_branch": "feature/sop-update-20231027",
    "commit_message": "docs: Add SOP for new feature verification",
    "pr_title": "SOP Update: Verification of New Feature X",
    "pr_body": "This PR introduces the Standard Operating Procedure for verifying new feature X. Please review and approve.",
    "file_path": "sop/new_feature_x_verification.md",
    "file_content": """
# SOP: New Feature X Verification

## 1. Purpose
This document describes the steps to verify the functionality of New Feature X.

## 2. Procedure
1. Navigate to the feature X dashboard.
2. Create a new item.
3. Verify item creation.

## 3. Approval
Please approve this PR to publish the new SOP.
"""
}
```

## 6. テスト実行手順

Temporal Workflowから`create_pull_request` Activityを呼び出し、疎通テストを実行するための具体的なステップを説明します。

### 6.1. Temporal Workflow と Activity の準備

`create_pull_request` Activityを呼び出すWorkflowを定義し、Workerに登録します。

1.  **Activity定義の用意**: `GitHubActivity`クラスの完全な実装をPythonファイル（例: `activities.py`）に保存します。

    ```python
    # activities.py
    import asyncio
    import os
    import subprocess
    import tempfile
    from pathlib import Path
    from temporalio import activity

    class GitHubActivity:
        # Workerプロセス固有の一時ディレクトリを使用
        _REPO_BASE: Path = Path(tempfile.gettempdir()) / "temporal_github_activity_repos"

        @activity.defn
        async def create_pull_request(self, params: dict) -> dict:
            activity.logger.info(f"Starting create_pull_request Activity with params: {params}")
            token = os.environ.get("GITHUB_TOKEN")
            if not token:
                raise EnvironmentError("GITHUB_TOKEN 環境変数が設定されていません。")

            repository = params["repository"]
            feature_branch = params["feature_branch"]
            file_path = params["file_path"]
            file_content = params["file_content"]
            commit_message = params["commit_message"]
            base_branch = params["base_branch"]
            pr_title = params["pr_title"]
            pr_body = params["pr_body"]

            # 一連のGit操作とPR作成
            repo_dir = await self._clone_or_update_repo(repository, token)
            await self._checkout_branch(repo_dir, feature_branch)
            await self._write_content(repo_dir, file_path, file_content)
            await self._commit_and_push(repo_dir, commit_message, feature_branch)
            pr_url = await self._submit_pr(
                repository,
                base_branch,
                feature_branch,
                pr_title,
                pr_body,
            )
            activity.logger.info(f"Pull Request created: {pr_url}")
            return {"pr_url": pr_url}

        async def _run_command(self, cmd: list[str], cwd: Path | None = None, check_output: bool = True) -> str:
            activity.logger.debug(f"Executing command: {' '.join(cmd)} in {cwd or Path.cwd()}")
            try:
                # subprocess.runはブロッキングなので、asyncio.to_threadで別スレッドで実行
                result = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    check=check_output,
                    env={**os.environ, "HOME": str(Path.home())} # gh auth login がHOMEディレクトリに設定ファイルを生成するため
                )
                if check_output:
                    activity.logger.debug(f"Command stdout: {result.stdout.strip()}")
                return result.stdout.strip()
            except subprocess.CalledProcessError as e:
                activity.logger.error(f"Command failed: {e.cmd}")
                activity.logger.error(f"Stderr: {e.stderr.strip()}")
                activity.logger.error(f"Stdout: {e.stdout.strip()}")
                raise RuntimeError(f"Command failed: {' '.join(e.cmd)}. Stderr: {e.stderr.strip()}") from e
            except Exception as e:
                activity.logger.error(f"An unexpected error occurred during command execution: {e}")
                raise RuntimeError(f"Unexpected error executing command: {' '.join(cmd)}") from e

        async def _clone_or_update_repo(self, repository: str, token: str) -> Path:
            repo_name = repository.split("/")[-1]
            repo_dir = self._REPO_BASE / repo_name
            
            # Use TOKEN for cloning for explicit access, gh auth might also cover this.
            # Direct embedding in URL is for explicit git clone/fetch.
            repo_credential_url = f"https://oauth2:{token}@github.com/{repository}.git"

            self._REPO_BASE.mkdir(parents=True, exist_ok=True) # ベースディレクトリを確実に作成

            if not repo_dir.exists():
                activity.logger.info(f"Cloning repository {repository} into {repo_dir}")
                await self._run_command(["git", "clone", repo_credential_url, str(repo_dir)], check_output=True)
            else:
                activity.logger.info(f"Repository {repository} already exists, updating in {repo_dir}")
                # リモートURLを更新して、確実に認証情報が適用されるようにする
                await self._run_command(["git", "-C", str(repo_dir), "remote", "set-url", "origin", repo_credential_url], check_output=True)
                # すべてのリモートブランチをフェッチし、HEADをベースブランチにハードリセット
                await self._run_command(["git", "-C", str(repo_dir), "fetch", "--all"], check_output=True)
                # 強制プッシュされる可能性のあるベースブランチにハードリセットしてクリーンな状態にする
                # NOTE: ここでは"main"ブランチを一時的に固定しています。実際にはbase_branchを引数で渡すなどの方が柔軟ですが、今回のテスト目的（新規PR作成）においては問題ありません。
                await self._run_command(["git", "-C", str(repo_dir), "reset", "--hard", "origin/main"], check_output=True)
            return repo_dir

        async def _checkout_branch(self, repo_dir: Path, feature_branch: str):
            activity.logger.info(f"Checking out/creating feature branch: {feature_branch} in {repo_dir}")
            # -B option creates or resets the branch if it already exists
            await self._run_command(["git", "-C", str(repo_dir), "checkout", "-B", feature_branch], check_output=True)

        async def _write_content(self, repo_dir: Path, file_path: str, file_content: str):
            full_path = repo_dir / file_path
            activity.logger.info(f"Writing content to file: {full_path}")
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(file_content)

        async def _commit_and_push(self, repo_dir: Path, commit_message: str, feature_branch: str):
            activity.logger.info(f"Staging changes in {repo_dir}")
            await self._run_command(["git", "-C", str(repo_dir), "add", "-A"], check_output=True)
            
            # 変更がない場合はコミットとプッシュをスキップ
            status_output = await self._run_command(["git", "-C", str(repo_dir), "status", "--porcelain"], check_output=True)
            if not status_output:
                activity.logger.info("No changes to commit. Skipping commit and push.")
                return

            activity.logger.info(f"Committing changes with message: '{commit_message}'")
            # コミットユーザー情報を明示的に設定
            await self._run_command(["git", "-C", str(repo_dir), "config", "user.name", "Temporal Worker"])
            await self._run_command(["git", "-C", str(repo_dir), "config", "user.email", "temporal-worker@local"])
            await self._run_command(["git", "-C", str(repo_dir), "commit", "-m", commit_message], check_output=True)

            activity.logger.info(f"Pushing feature branch {feature_branch} to origin ({repository}) with --force")
            await self._run_command(["git", "-C", str(repo_dir), "push", "--force", "origin", feature_branch], check_output=True)

        async def _submit_pr(self, repository: str, base_branch: str, feature_branch: str, pr_title: str, pr_body: str) -> str:
            activity.logger.info(f"Submitting Pull Request for {feature_branch} into {base_branch} in {repository}")
            
            # gh pr create コマンドは、同じヘッドブランチを持つ既存のPRが存在する場合、
            # 新しいPRを作成せず、既存のPRのURLを返すか、ブラウザで開く挙動をします。
            # そのため、事前に gh pr list でチェックする必要はありません。
            create_pr_cmd = [
                "gh", "pr", "create",
                "--repo", repository,
                "--base", base_branch,
                "--head", feature_branch,
                "--title", pr_title,
                "--body", pr_body,
            ]
            
            # gh pr create の標準出力は、通常、作成されたPRのURLです。
            pr_output = await self._run_command(create_pr_cmd, check_output=True)
            pr_url = pr_output.strip()
            
            if not pr_url.startswith("https://github.com/"):
                raise RuntimeError(f"Failed to create PR or invalid URL returned by 'gh pr create': {pr_output}")
                
            activity.logger.info(f"Pull Request created/found: {pr_url}")
            return pr_url
    ```

2.  **Workflow定義の作成**: `create_pull_request` Activityを呼び出すWorkflowをPythonファイル（例: `workflow.py`）に作成します。

    ```python
    # workflow.py
    from temporalio.workflow import workflow_method, ActivityMethod, workflow, activity_method
    from activities import GitHubActivity # Activityクラスをインポート

    @workflow.defn
    class GitHubPRTestWorkflow:
        @workflow.run
        async def run(self, params: dict) -> dict:
            # create_pull_request activity を呼び出す
            # GitHubActivityクラスのcreate_pull_requestメソッドをActivityMethodとして定義
            self.create_pr: ActivityMethod[dict, dict] = activity_method(GitHubActivity.create_pull_request)
            pr_result = await self.create_pr(params)
            workflow.logger.info(f"Pull Request created: {pr_result['pr_url']}")

            # ここに approve_pr Signal を待つロジックを追加可能 (Human-in-the-Loopフローの次ステップ)
            # await workflow.wait_for_external_signal("approve_pr")

            return pr_result
    ```

3.  **Workerの起動**: `workflow.py`と`activities.py`を同じディレクトリに置き、Workerを起動します。

    ```python
    # worker.py
    import asyncio
    from temporalio.client import Client
    from temporalio.worker import Worker
    from workflow import GitHubPRTestWorkflow # 作成したWorkflow
    from activities import GitHubActivity     # 作成したActivity

    async def main():
        client = await Client.connect("localhost:7233") # Temporal Cluster のアドレス
        worker = Worker(
            client,
            task_queue="github-pr-test-task-queue", # 任意のタスクキュー名
            workflows=[GitHubPRTestWorkflow],
            # Activityクラスを登録。Workerがインスタンスを管理します。
            # Activityメソッドに@activity.defnデコレータが付与されている必要があります。
            activities=[GitHubActivity], 
        )
        print("Worker started. Press Ctrl+C to exit.")
        await worker.run()

    if __name__ == "__main__":
        asyncio.run(main())
    ```
    ```bash
    python worker.py
    ```
    Workerが正常に起動し、タスクキュー`github-pr-test-task-queue`でWorkflowとActivityを処理できる状態になっていることを確認します。

### 6.2. テスト用の `params` 値の準備

セクション5で説明した`params`辞書の構造に従い、テスト環境に合わせた値を準備します。

*   **`repository`**: ご自身のGitHubユーザー名とテスト用リポジリ名に置き換えます。
*   **`feature_branch`**: テストごとにユニークなブランチ名を推奨します（例: `feature/sop-test-pr-YYYYMMDD-HHMMSS`）。
*   **`file_content`**: テストの識別ができるような内容を含めると良いでしょう。

```python
# client.py
import asyncio
from temporalio.client import Client
from datetime import datetime

async def main():
    client = await Client.connect("localhost:7233") # Temporal Cluster のアドレス

    # 現在日時に基づいてユニークなブランチ名とファイル名を生成
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    feature_branch_name = f"feature/sop-test-pr-{timestamp}"
    file_path_name = f"temporal-sop-test/test_file_{timestamp}.md"

    params = {
        "repository": "YOUR_GITHUB_USERNAME/YOUR_TEST_REPO", # ここを実際の情報に更新
        "base_branch": "main",
        "feature_branch": feature_branch_name,
        "commit_message": f"feat: Add Temporal SOP test file {timestamp}",
        "pr_title": f"SOP Test PR for create_pull_request Activity ({timestamp})",
        "pr_body": f"This Pull Request was automatically generated by the Temporal create_pull_request Activity as part of an SOP test.\n\nTimestamp: {timestamp}",
        "file_path": file_path_name,
        "file_content": f"# Temporal SOP Test File\n\nThis file was created by Temporal Workflow for testing purpose.\nTimestamp: {timestamp}\n",
    }

    print(f"Starting workflow with params:\n{params}")

    result = await client.execute_workflow(
        "GitHubPRTestWorkflow", # Workflow名
        params,
        id=f"github-pr-test-workflow-{timestamp}",
        task_queue="github-pr-test-task-queue", # Worker と同じタスクキュー
    )
    print(f"Workflow finished. Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 6.3. Temporal Workflow のトリガー方法

上記`client.py`スクリプトを実行してWorkflowをトリガーします。

```bash
python client.py
```

### 6.4. Activity の実行監視

Workflowがトリガーされると、Temporal Workerは`create_pull_request` Activityを実行します。以下の方法で実行を監視できます。

*   **Temporal Web UI**:
    1.  Temporal Web UI（通常は`http://localhost:8080`）にアクセスします。
    2.  左側のナビゲーションで「Workflows」をクリックします。
    3.  `workflow ID` (例: `github-pr-test-workflow-YYYYMMDDHHMMSS`) で検索し、該当するWorkflow実行を見つけます。
    4.  Workflowの詳細ページで「Events」タブをクリックし、`create_pull_request` Activityがスケジュールされ、実行され、完了したことを確認します。Activityの入力と出力も確認できます。
*   **Workerのログ**:
    `worker.py`を実行しているターミナルで、Activityが実行される際のログメッセージ（`git`や`gh`コマンドの出力、エラーなど）を確認します。`_run_command`ヘルパーメソッドの`activity.logger.debug`メッセージを表示するには、Workerのログレベルを調整する必要がある場合があります。
*   **クライアントスクリプトの出力**:
    `client.py`を実行しているターミナルで、Workflowの最終的な実行結果（Activityからの`pr_url`を含む辞書）が出力されることを確認します。

## 7. 検証方法と結果確認

Activityの実行結果が期待通りであるかを確認する手順を説明します。

### 7.1. GitHub上でのPull Requestの作成確認

1.  **GitHubリポジリへのアクセス**: Webブラウザで、テストに使用したGitHubリポジリ（例: `YOUR_GITHUB_USERNAME/YOUR_TEST_REPO`）にアクセスします。
2.  **Pull requests タブの確認**: リポジリのページで「Pull requests」タブをクリックします。
3.  **新規PRの確認**: `create_pull_request` Activityによって作成された新しいPull Requestが一覧に表示されていることを確認します。タイトルは`pr_title`で指定した内容と一致するはずです。

### 7.2. PRのタイトル・本文・変更内容の確認

作成されたPull Requestの詳細ページを開き、以下の項目を確認します。

*   **PRタイトル**: `params["pr_title"]`で指定した内容と完全に一致すること。
*   **PR本文**: `params["pr_body"]`で指定した内容と完全に一致すること。
*   **変更内容 (Files changed)**: 「Files changed」タブを開き、`params["file_path"]`で指定したパスに新しいファイルが作成されており、その内容が`params["file_content"]`と完全に一致することを確認します。既存のファイルが変更された場合は、その差分も確認します。
*   **ベースブランチとヘッドブランチ**: PRが`params["base_branch"]`をターゲットとし、`params["feature_branch"]`からの変更を提案していることを確認します。
*   **コミット履歴**: 「Commits」タブを開き、`params["commit_message"]`で指定したコミットメッセージを持つコミットが1つ以上存在することを確認します。コミットの作成者が`Temporal Worker <temporal-worker@local>`になっていることを確認します。

### 7.3. PRが後の `approve_pr Signal` 処理に繋がる状態であることの検証

*   **PRのステータス**: Pull Requestが「Open」ステータスであることを確認します。これにより、後続の`approve_pr Signal`を受け取る準備ができている状態です。
*   **レビューア**: 必要に応じて、Workflowの後続処理でレビューアが設定される構成の場合、その設定も確認します。本Activity自体はレビューアを設定しませんが、Human-in-the-Loopフロー全体の観点からは重要です。

### 7.4. Activityの戻り値の確認

*   **クライアントスクリプトの出力**: `client.py`実行時に出力されたWorkflowの最終結果に、作成されたPRのURL (`pr_url`) が含まれていることを確認します。
    ```
    Workflow finished. Result: {'pr_url': 'https://github.com/YOUR_GITHUB_USERNAME/YOUR_TEST_REPO/pull/N'}
    ```
    この`pr_url`が、GitHub上で確認したPRのURLと一致することを確認してください。

## 8. トラブルシューティング

テスト実行中によく発生する可能性のある問題とその解決策を以下に示します。

### 8.1. `EnvironmentError: GITHUB_TOKEN 環境変数が設定されていません。`

*   **原因**: Temporal Workerが動作する環境で`GITHUB_TOKEN`環境変数が設定されていないか、Workerプロセスから参照できません。
*   **解決策**:
    1.  セクション3.3に従って`GITHUB_TOKEN`が正しく設定されているか再確認します。
    2.  Workerを起動しているシェルで`echo $GITHUB_TOKEN`（Linux/macOS）または`echo $env:GITHUB_TOKEN`（PowerShell）を実行し、値が表示されるか確認します。
    3.  Workerがサービスとして起動している場合、サービスの設定ファイル（例: Systemdの`.service`ファイル）や起動スクリプト内で`GITHUB_TOKEN`がエクスポートされていることを確認します。
    4.  コンテナ環境の場合、コンテナ定義で環境変数が渡されていることを確認します。

### 8.2. `RuntimeError: Command failed: [...]`

これは`git CLI`または`gh CLI`コマンドの実行中にエラーが発生したことを示します。エラーメッセージの詳細を確認することが重要です。`_run_command`ヘルパーメソッドは、`subprocess.CalledProcessError`をキャッチし、より詳細な`RuntimeError`をスローします。

*   **一般的な原因と解決策**:
    1.  **権限不足**:
        *   **原因**: `GITHUB_TOKEN`に必要なリポジリへの書き込み権限（`repo`スコープなど）がないため、`git push`や`gh pr create`が失敗します。
        *   **解決策**: セクション3.3で説明されているように、`GITHUB_TOKEN`が適切なスコープ（少なくとも`repo`）で生成されていることを確認し、トークンを再発行して環境変数に設定し直します。
    2.  **`git`/`gh CLI`がインストールされていないか、PATHが通っていない**:
        *   **原因**: Workerが動作する環境に`git`または`gh`コマンドが見つからない。
        *   **解決策**: セクション3.1および3.2に従って、両CLIツールがインストールされ、Workerプロセスの`PATH`環境変数に含まれていることを確認します。`which git`や`which gh`でパスを確認できます。
    3.  **リポジリが見つからない/URLが無効**:
        *   **原因**: `params["repository"]`の値が誤っているか、GitHub上で存在しないリポジリを指定しています。
        *   **解決策**: `params`辞書内の`repository`キーの値が`owner/repo`形式で正確であることを確認します。GitHub上でそのリポジリが存在し、アクセス可能であることを確認します。
    4.  **ブランチが見つからない/競合**:
        *   **原因**: `base_branch`が存在しない、または`feature_branch`の強制プッシュ中に競合が発生しました（`--force`オプションにより通常は上書きされますが、それでも問題が発生する場合）。
        *   **解決策**: `params`辞書内の`base_branch`が対象リポジリに存在することを確認します。`feature_branch`を毎回ユニークな名前にすることで、競合のリスクを減らすことができます。
    5.  **`gh CLI`認証の失敗**:
        *   **原因**: `gh auth login`が正常に完了していないか、セッションが期限切れです。
        *   **解決策**: `gh auth status`を実行し、認証状態を確認します。必要に応じて`gh auth login`を再度実行し、認証を更新します。

*   **エラーメッセージの確認**:
    `RuntimeError`のメッセージに含まれる`Stderr`の内容を詳細に確認することが最も重要です。
    ```
    # Workerログの例 (Stderr出力)
    temporal.worker -- Workflow Run ID: ... Activity Task: create_pull_request -- ERROR: RuntimeError: Command failed: git -C /tmp/... push --force origin feature/test. Stderr: remote: Repository not found. fatal: repository 'https://ghp_...github.com/owner/repo.git/' not found
    ```
    この例では「Repository not found」というメッセージから、リポジリ名または認証の問題が示唆されます。

### 8.3. PRが作成されないがエラーも発生しない

*   **原因**: `_submit_pr`ヘルパーメソッドが内部で呼び出す`gh pr create`コマンドは、同じ`head`ブランチを持つPRが既に存在する場合、新しいPRを作成せずに既存PRのURLを返します。この場合、新しいPRは作成されません。
*   **解決策**:
    1.  Temporal Web UIでWorkflow実行の詳細を確認し、Activityの出力に`pr_url`が返されているかを確認します。
    2.  `pr_url`が返されている場合、そのURLにアクセスして、既存のPRが意図されたものであることを確認します。
    3.  新しいPRを確実に作成したい場合は、毎回ユニークな`feature_branch`名を指定してください。`client.py`でタイムスタンプをブランチ名に含める方法は、この問題を回避するのに有効です。

## 9. 関連情報

本SOPに関連する追加情報やリソースへの参照を提供します。

*   **Temporal ドキュメント**:
    *   [Temporal Python SDK ドキュメント](https://docs.temporal.io/python/activities)
    *   [Temporal Activities](https://docs.temporal.io/dev-guide/typescript/activities)
    *   [Temporal Signals](https://docs.temporal.io/dev-guide/typescript/signals)
*   **GitHub API リファレンス**:
    *   [GitHub REST API - Pull Requests](https://docs.github.com/en/rest/pulls)
    *   [GitHub Personal Access Token スコープ](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#available-scopes)
    *   [Fine-grained Personal Access Tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token)
*   **Git CLI 公式ドキュメント**:
    *   [Git ドキュメント](https://git-scm.com/doc)
*   **GitHub CLI (gh) 公式ドキュメント**:
    *   [GitHub CLI マニュアル](https://cli.github.com/manual/)