# I'm not sure if it is necessary to run this query.

def pull_commits_info_for_diff(self, repo_owner: str, repo_name: str, pr_id: int, page_token: str = None, simple: bool = True):
    """
        ...
    """

    graphql_query: dict = {
      "operationName": "PullCommitsForDiffSelector",
      "variables": {
        "ownerName": repo_owner,
        "repoName": repo_name,
        "pullId": str(pr_id)
      },
      "query": "query PullCommitsForDiffSelector($repoName: String!, $ownerName: String!, $pullId: String!) {  pull(repoName: $repoName, ownerName: $ownerName, pullId: $pullId) {    _id    summary {      ...PullSummaryForDiffSelector      __typename    }    __typename  }}fragment PullSummaryForDiffSelector on PullSummary {  _id  commits {    ...CommitListForDiffSelector    __typename  }  mergeState {    premergeFromCommit    premergeToCommit    mergeBaseCommit    __typename  }  __typename}fragment CommitListForDiffSelector on CommitList {  list {    ...CommitForDiffSelector    __typename  }  nextPageToken  __typename}fragment CommitForDiffSelector on Commit {  _id  commitId  message  committedAt  committer {    displayName    __typename  }  __typename}"
    }

    # Allows the Caller To Start From A Specific Page
    if page_token is not None:
        graphql_query["variables"]["pageToken"] = page_token

    has_next_page: bool = True
    while has_next_page:
        result, status_code, _ = self.perform_api_operation(graphql_query=graphql_query)
        pr_meta = result["data"]["pull"]
        commit_list = pr_meta["summary"]["commits"]["list"]

        # Check For Next Page Token If Any, Otherwise Set The Loop To Close
        if "nextPageToken" not in pr_meta["summary"]["commits"] or pr_meta["summary"]["commits"]["nextPageToken"].strip() == "":
            has_next_page: bool = False
        else:
            graphql_query["variables"]["pageToken"] = pr_meta["summary"]["commits"]["nextPageToken"]

        if simple:
            pass
        else:
            yield result, status_code
