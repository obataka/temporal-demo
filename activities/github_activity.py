"""
GitHub PR 作成 Activity — git CLI と gh CLI を用いてリポジトリを操作し Pull Request を開通する。

認証情報は環境変数 GITHUB_TOKEN から取得する。
git 操作は subprocess + git CLI、PR 作成は gh CLI を使用する。
"""

import os
import subprocess
import tempfile
from pathlib import Path

from temporalio import activity


class GitHubActivity:
    """
    Temporal Activity クラス。GitHub への Push と PR 作成を担う。

    認証情報は環境変数 GITHUB_TOKEN から取得する。
    git 操作は subprocess + git CLI、PR 作成は gh CLI を使用する。
    _REPO_BASE はテストで差し替え可能なクラス変数として公開している。
    """

    _REPO_BASE: Path = Path(tempfile.gettempdir()) / "temporal_github"

    # ─── Public Activity ─────────────────────────────────────────────────────

    @activity.defn
    async def create_pull_request(self, params: dict) -> dict:
        """
        SOP または修正コードをリポジトリへ Push し、Pull Request を作成する。

        :param params: repository / base_branch / feature_branch / commit_message /
                       pr_title / pr_body / file_path / file_content を含む辞書
        :returns: {"pr_url": "https://github.com/.../pull/N"}
        :raises EnvironmentError: GITHUB_TOKEN が未設定の場合
        :raises subprocess.CalledProcessError: git / gh 操作失敗時
        """
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise EnvironmentError("GITHUB_TOKEN が設定されていません。")

        repo_dir = self._clone_or_update_repo(params["repository"], token)
        self._checkout_branch(repo_dir, params["feature_branch"])
        self._write_content(repo_dir, params["file_path"], params["file_content"])
        self._commit_and_push(repo_dir, params["commit_message"], params["feature_branch"])
        pr_url = self._submit_pr(
            params["repository"],
            params["base_branch"],
            params["feature_branch"],
            params["pr_title"],
            params["pr_body"],
        )
        return {"pr_url": pr_url}

    # ─── Private Helpers ─────────────────────────────────────────────────────

    def _clone_or_update_repo(self, repository: str, token: str) -> Path:
        """
        リポジトリをローカルにクローンするか、既存なら最新化する。

        :param repository: "owner/repo" 形式のリポジトリ名
        :param token: GitHub Personal Access Token
        :returns: ローカルリポジトリディレクトリの Path
        """
        repo_dir = self._REPO_BASE / repository.replace("/", "_")
        clone_url = f"https://{token}@github.com/{repository}.git"

        if repo_dir.exists():
            subprocess.run(
                ["git", "-C", str(repo_dir), "remote", "set-url", "origin", clone_url],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(repo_dir), "fetch", "--all"],
                check=True, capture_output=True,
            )
        else:
            repo_dir.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", clone_url, str(repo_dir)],
                check=True, capture_output=True,
            )
        return repo_dir

    def _checkout_branch(self, repo_dir: Path, branch: str) -> None:
        """
        feature ブランチをチェックアウトする（既存なら上書きリセット）。

        :param repo_dir: ローカルのリポジトリディレクトリ
        :param branch: チェックアウトするブランチ名
        """
        subprocess.run(
            ["git", "-C", str(repo_dir), "checkout", "-B", branch],
            check=True, capture_output=True,
        )

    def _write_content(self, repo_dir: Path, file_path: str, content: str) -> None:
        """
        リポジトリ内の指定パスにコンテンツを書き込む（親ディレクトリを自動作成）。

        :param repo_dir: ローカルのリポジトリディレクトリ
        :param file_path: リポジトリルートからの相対ファイルパス
        :param content: 書き込むコンテンツ文字列
        """
        target = repo_dir / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def _commit_and_push(self, repo_dir: Path, message: str, branch: str) -> None:
        """
        全変更をステージング・コミットし、強制プッシュする。

        差分がない場合はコミットをスキップし force-push のみ実行する（冪等性保証）。

        :param repo_dir: ローカルのリポジトリディレクトリ
        :param message: コミットメッセージ
        :param branch: プッシュするブランチ名
        """
        subprocess.run(
            ["git", "-C", str(repo_dir), "add", "-A"],
            check=True, capture_output=True,
        )
        diff = subprocess.run(
            ["git", "-C", str(repo_dir), "diff", "--cached", "--quiet"],
            capture_output=True,
        )
        if diff.returncode != 0:
            subprocess.run(
                ["git", "-C", str(repo_dir), "config", "user.email", "temporal-worker@local"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(repo_dir), "config", "user.name", "Temporal Worker"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(repo_dir), "commit", "-m", message],
                check=True, capture_output=True,
            )
        subprocess.run(
            ["git", "-C", str(repo_dir), "push", "--force", "origin", branch],
            check=True, capture_output=True,
        )

    def _submit_pr(
        self,
        repository: str,
        base: str,
        head: str,
        title: str,
        body: str,
    ) -> str:
        """
        gh CLI で PR を作成する。同ブランチの PR が既存なら URL をそのまま返す。

        :param repository: "owner/repo" 形式のリポジトリ名
        :param base: マージ先ブランチ名
        :param head: feature ブランチ名
        :param title: PR タイトル
        :param body: PR 本文
        :returns: PR の URL 文字列
        """
        check = subprocess.run(
            ["gh", "pr", "list", "--head", head, "--repo", repository,
             "--json", "url", "--jq", ".[0].url"],
            capture_output=True, text=True,
        )
        existing_url = check.stdout.strip()
        if existing_url:
            return existing_url

        result = subprocess.run(
            ["gh", "pr", "create",
             "--repo", repository,
             "--base", base,
             "--head", head,
             "--title", title,
             "--body", body],
            check=True, capture_output=True, text=True,
        )
        return result.stdout.strip()
