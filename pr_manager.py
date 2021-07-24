import requests
import json
import os


class NoAuthException(Exception):
    """
        Thrown when a token is not given.
    """

    pass


class NeedAtLeastOneOptionalArgumentException(Exception):
    """
        Thrown when none of the optional arguments are specified and at least one optional argument is needed.
    """

    pass


class APIServerException(Exception):
    """
        Thrown when the GraphQL API throws an exception.
    """

    pass


class PRManager:
    def __init__(self, token: str = None, token_file: str = None, user_agent: str = "Alexis' Private API Client For Bounties"):
        """
            Required to setup the private api client.

            @param token: To provide the dolthubToken cookie value directly.
            @param token_file: To provide the file with the dolthubToken cookie value.
            @param user_agent: To change the user agent.
            @return: Nothing
        """

        self.user_agent = user_agent
        self.graphql_url = "https://www.dolthub.com/graphql"

        self.allowed_status_codes = [200, 301, 302, 418]  # 418 is the Teapot Exception Code
        self.allowed_pr_states = ["Open", "Closed", "Merged"]  # Currently not in use

        if token is None and token_file is not None:
            if not os.path.exists(token_file):
                raise NoAuthException("The token file does not exist.")

            self.token = open(token_file, mode="r").read().strip()
        elif token is not None:
            self.token = token
        else:
            raise NoAuthException("Cannot use authenticated functions without a token. Please provide the value from the dolthubToken cookie.")

    def perform_api_operation(self, graphql_query: dict):
        """
            Performs a raw API operation.
            This is for more advanced operations or if a new feature is implemented on Dolthub.

            @param graphql_query: GraphQL Query as Dictionary
            @return: JSON Results, HTTP Status Code, and Response object from operation
        """

        headers: dict = {
            "User-Agent": self.user_agent,
            "Cookie": f"dolthubToken={self.token}"
        }

        response = requests.post(url=self.graphql_url, json=graphql_query, headers=headers)

        result = json.loads(response.text)

        if response.status_code not in self.allowed_status_codes:
            raise APIServerException("GraphQL API threw a HTTP Status Code exception", result, response.status_code, response)

        if "errors" in result:
            raise APIServerException("GraphQL API threw an exception", result, response.status_code, response)

        return result, response.status_code, response

    def lookup_pr(self, repo_owner: str, repo_name: str, pr_id: int, simple: bool = True):
        """
            Lookup detailed information on the PR in question.

            Used by the update_pr function if not all optional values are specified in order to fill in the missing information.

            @param repo_owner: The owner of the repo where the PR resides. Not the submitter of the PR.
            @param repo_name: The name of the repo where the PR resides. Not the name of the fork that the PR came from.
            @param pr_id: The id of the PR as seen in the PR list of the repo.

            Optional Values
            @param simple: Boolean that defaults to True in order to provide a consistent and simple dictionary that'll remain the same even when the API changes. Changing this value to False will return the raw API body as a dictionary.

            @return: Information about the PR requested and if simple mode is turned off, also the HTTP status code.
        """

        graphql_query: dict = {
          "operationName": "PullForPullDetailsQuery",
          "variables": {
            "ownerName": repo_owner,
            "repoName": repo_name,
            "pullId": str(pr_id)
          },
          "query": "query PullForPullDetailsQuery($repoName: String!, $ownerName: String!, $pullId: String!) {  pull(repoName: $repoName, ownerName: $ownerName, pullId: $pullId) {    ...PullForPullDetails    __typename  }}fragment PullForPullDetails on Pull {  _id  pullId  state  title  description  fromBranchName  fromBranchOwnerName  fromBranchRepoName  toBranchName  toBranchOwnerName  toBranchRepoName  creatorName  isFork  __typename}"
        }

        result, status_code, _ = self.perform_api_operation(graphql_query=graphql_query)

        if simple:
            pr_meta: dict = result["data"]["pull"]
            simple_result: dict = {
                "id": int(pr_meta["pullId"]),
                "state": pr_meta["state"],
                "title": pr_meta["title"],
                "message": pr_meta["description"],
                "creator": pr_meta["creatorName"],
                "fork": bool(pr_meta["isFork"]),

                # Source Of Data To Merge
                "source": {
                    "branch": pr_meta["fromBranchName"],
                    "owner": pr_meta["fromBranchOwnerName"],
                    "repo": pr_meta["fromBranchRepoName"]
                },

                # Destination Of Where To Merge Data
                "destination": {
                    "branch": pr_meta["toBranchName"],
                    "owner": pr_meta["toBranchOwnerName"],
                    "repo": pr_meta["toBranchRepoName"]
                }
            }

            return simple_result

        return result, status_code

    def update_pr(self, repo_owner: str, repo_name: str, pr_id: int, pr_state: str = None, pr_title: str = None, pr_message: str = None):
        """
            To update the Pull Request in question. Due to the nature of the API, everything has to be updated, even if you want to just close the PR.
            To help facilitate simple actions, the PR's existing data will be automatically pulled if an optional value is set to None.

            If merging the PR, this function will handle merging for you and will return the merge status of the PR appended to the PR update status.
            If you don't want to update the PR, but just want to merge the PR, then call the merge_pr function instead.

            @param repo_owner: The owner of the repo where the PR resides. Not the submitter of the PR.
            @param repo_name: The name of the repo where the PR resides. Not the name of the fork that the PR came from.
            @param pr_id: The id of the PR as seen in the PR list of the repo.

            Optional Values - These values change the state of the PR.
            @param pr_state: Can be "Open", "Closed", or "Merged". These values are case-sensitive.
            @param pr_title: The title of the PR as seen in the PR list of the repo.
            @param pr_message: The message of the PR as seen in the PR details page. This is not a PR comment. If you want to set this as empty, use an empty string. Setting this to None will just keep the same message as before.

            @return: A tuple of the HTTP Status Code and the response body read as JSON. The response body is first and then the status code comes second.
        """

        # At least one optional argument is required, it doesn't matter which one.
        if pr_state is None and pr_title is None and pr_message is None:
            raise NeedAtLeastOneOptionalArgumentException("Specify at least one of pr_state, pr_title, or pr_message.")

        # Handle Merging For Caller
        should_merge: bool = False
        if pr_state == "Merged":
            should_merge: bool = True
            pr_state = None  # The GraphQL API falsly thinks the PR is merged when setting it to Merged before actually merging it.

        # If we don't have every value filled out, find out the existing values from the PR.
        if pr_state is None or pr_title is None or pr_message is None:
            existing_values = self.lookup_pr(repo_owner=repo_owner, repo_name=repo_name, pr_id=pr_id, simple=True)

            if pr_state is None:
                pr_state = existing_values["state"]

            if pr_title is None:
                pr_title = existing_values["title"]

            if pr_message is None:
                pr_message = existing_values["message"]

        graphql_query: dict = {
          "operationName": "UpdatePullInfo",
          "variables": {
            "_id": f"repositoryOwners/{repo_owner}/repositories/{repo_name}/pulls/{pr_id}",
            "state": pr_state,
            "title": pr_title,
            "description": pr_message
          },
          "query": "mutation UpdatePullInfo($_id: String!, $title: String!, $description: String!, $state: PullState!) {  updatePull(_id: $_id, title: $title, description: $description, state: $state) {    _id    __typename  }}"
        }

        result, status_code, _ = self.perform_api_operation(graphql_query=graphql_query)

        if should_merge:
            merge_result, merge_status_code = self.merge_pr(repo_owner=repo_owner, repo_name=repo_name, pr_id=pr_id)
            return result, status_code, merge_result, merge_status_code

        return result, status_code

    def merge_pr(self, repo_owner: str, repo_name: str, pr_id: int):
        """
            For when you want to merge an existing PR.

            @param repo_owner: The owner of the repo where the PR resides. Not the submitter of the PR.
            @param repo_name: The name of the repo where the PR resides. Not the name of the fork that the PR came from.
            @param pr_id: The id of the PR as seen in the PR list of the repo.

            @return: A tuple of the HTTP Status Code and the response body read as JSON. The response body is first and then the status code comes second.
        """

        graphql_query: dict = {
          "operationName": "MergePull",
          "variables": {
            "ownerName": repo_owner,
            "repoName": repo_name,
            "pullId": str(pr_id)
          },
          "query": "mutation MergePull($repoName: String!, $ownerName: String!, $pullId: String!) {  mergePull(repoName: $repoName, ownerName: $ownerName, pullId: $pullId) {    ...PullForPullDetails    __typename  }}fragment PullForPullDetails on Pull {  _id  pullId  state  title  description  fromBranchName  fromBranchOwnerName  fromBranchRepoName  toBranchName  toBranchOwnerName  toBranchRepoName  creatorName  isFork  __typename}"
        }

        result, status_code, _ = self.perform_api_operation(graphql_query=graphql_query)
        return result, status_code

    def comment_on_pr(self, repo_owner: str, repo_name: str, pr_id: int, message: str):
        """
            For when you want to comment on a PR.
            The API does not check for duplicate comments, so you'll want to do that yourself.

            @param repo_owner: The owner of the repo where the PR resides. Not the submitter of the PR.
            @param repo_name: The name of the repo where the PR resides. Not the name of the fork that the PR came from.
            @param pr_id: The id of the PR as seen in the PR list of the repo.

            @return: A tuple of the HTTP Status Code and the response body read as JSON. The response body is first and then the status code comes second.
        """

        graphql_query: dict = {
          "operationName": "CreatePullComment",
          "variables": {
            "ownerName": repo_owner,
            "repoName": repo_name,
            "parentId": str(pr_id),
            "comment": str(message)
          },
          "query": "mutation CreatePullComment($repoName: String!, $ownerName: String!, $parentId: String!, $comment: String!) {  createPullComment(    repoName: $repoName    ownerName: $ownerName    pullId: $parentId    comment: $comment  ) {    ...PullSummaryForPullDetails    __typename  }}fragment PullSummaryForPullDetails on PullSummary {  _id  __typename}"
        }

        result, status_code, _ = self.perform_api_operation(graphql_query=graphql_query)
        return result, status_code

    def create_pr(self, source_repo_owner: str, source_repo_name: str, source_branch: str,
                  destination_repo_owner: str, destination_repo_name: str, destination_branch: str,
                  pr_title: str = "", pr_message: str = "", simple: bool = True):
        """
            Creates a new PR with the already uploaded branch that is to be merged with the destination branch.

            @param source_repo_owner: The owner of the repo the PR is coming from.
            @param source_repo_name: The name of the repo the PR is coming from.
            @param source_branch: The name of the branch the PR is coming from.

            @param destination_repo_owner: The owner of the repo the PR is merging into.
            @param destination_repo_name: The name of the repo the PR is merging into.
            @param destination_branch: The name of the branch the PR is merging into.

            Optional Values
            @param pr_title: The title of the PR as seen in the PR list of the repo. This is optional, but you should set a custom title.
            @param pr_message: The message of the PR as seen in the PR details page. This is not a PR comment. If you want to set this as empty, use an empty string.
            @param simple: Boolean that defaults to True in order to provide a consistent and simple dictionary that'll remain the same even when the API changes. Changing this value to False will return the raw API body as a dictionary.
        """

        graphql_query: dict = {
          "operationName": "CreatePullRequestWithForks",
          "variables": {
            "title": pr_title,
            "description": pr_message,
            "fromBranchName": source_branch,
            "toBranchName": destination_branch,
            "fromBranchOwnerName": source_repo_owner,
            "fromBranchRepoName": source_repo_name,
            "toBranchOwnerName": destination_repo_owner,
            "toBranchRepoName": destination_repo_name,

            # As far as I can tell, this is always the same as the destination versions.
            "parentOwnerName": destination_repo_owner,
            "parentRepoName": destination_repo_name
          },
          "query": "mutation CreatePullRequestWithForks($title: String!, $description: String!, $fromBranchName: String!, $toBranchName: String!, $fromBranchRepoName: String!, $fromBranchOwnerName: String!, $toBranchRepoName: String!, $toBranchOwnerName: String!, $parentRepoName: String!, $parentOwnerName: String!) {  createPullWithForks(    title: $title    description: $description    fromBranchName: $fromBranchName    toBranchName: $toBranchName    fromBranchOwnerName: $fromBranchOwnerName    fromBranchRepoName: $fromBranchRepoName    toBranchOwnerName: $toBranchOwnerName    toBranchRepoName: $toBranchRepoName    parentRepoName: $parentRepoName    parentOwnerName: $parentOwnerName  ) {    _id    pullId    __typename  }}"
        }

        result, status_code, _ = self.perform_api_operation(graphql_query=graphql_query)

        if simple:
            # I could return the simple value of lookup_pr, but I feel like this is not needed.
            # I also intentionally made this a dictionary incase I needed to add more data in the future.
            # That way I won't break backwards compatibility with existing code.
            pr_meta: dict = result["data"]["createPullWithForks"]
            simple_result: dict = {
                "id": int(pr_meta["pullId"])
            }

            return simple_result

        return result, status_code


if __name__ == "__main__":
    try:
        manager = PRManager(token_file="token.txt")

        # Update PR Demos
        # results, status_code = manager.update_pr(repo_owner="alexis-evelyn", repo_name="test-forking", pr_id=4, pr_state="Open")
        # results, status_code, merged_results, merged_status_code = manager.update_pr(repo_owner="alexis-evelyn", repo_name="test-forking", pr_id=3, pr_state="Merged")

        # Create and Then Lookup PR Demo
        # create_pr_result = manager.create_pr(source_repo_owner="alexis-evelyn", source_repo_name="test-forking", source_branch="test_pr_script_5",
        #                                      destination_repo_owner="alexis-evelyn", destination_repo_name="test-forking", destination_branch="master")
        # lookup_pr_results = manager.lookup_pr(repo_owner="alexis-evelyn", repo_name="test-forking", pr_id=create_pr_result["id"])

        # print(f"Create PR Result: {create_pr_result}")
        # print(f"Lookup PR Result: {lookup_pr_results}")

        # Commenting On PR Demo
        # manager.comment_on_pr(repo_owner="alexis-evelyn", repo_name="test-forking", pr_id=5, message="This is a test comment 2")

        # Lookup PR Demo
        lookup_pr_results = manager.lookup_pr(repo_owner="dolthub", repo_name="logo-2k-extended", pr_id=23)

        # PR Metadata
        pr_id = lookup_pr_results["id"]
        pr_state = lookup_pr_results["state"]
        pr_title = lookup_pr_results["title"]
        pr_message = lookup_pr_results["message"]
        pr_creator = lookup_pr_results["creator"]
        is_fork = lookup_pr_results["fork"]

        # Source of Data To Merge
        source_branch = lookup_pr_results["source"]["branch"]
        source_owner = lookup_pr_results["source"]["owner"]
        source_repo = lookup_pr_results["source"]["repo"]

        # Destination Where To Merge Data
        destination_branch = lookup_pr_results["destination"]["branch"]
        destination_owner = lookup_pr_results["destination"]["owner"]
        destination_repo = lookup_pr_results["destination"]["repo"]

        print(f"PR {pr_id} - State: {pr_state} - Title: `{pr_title}` - Message: `{pr_message}` - Creator: {pr_creator} - Fork: {is_fork}")
        print(f"PR {pr_id} - Source: {source_owner}/{source_repo}/{source_branch}")
        print(f"PR {pr_id} - Destination: {destination_owner}/{destination_repo}/{destination_branch}")
    except NoAuthException as e:
        print(f"NoAuthException: {e}")
    except NeedAtLeastOneOptionalArgumentException as e:
        print(f"NeedAtLeastOneOptionalArgumentException: {e}")
    except APIServerException as e:
        message, result, status_code, response = e.args

        if "errors" in result:
            for error in result["errors"]:
                if "message" in error:
                    print(f"APIServerException: {message} - {error['message']}")
        else:
            print(f"APIServerException: {message} - Status Code: {status_code}")
