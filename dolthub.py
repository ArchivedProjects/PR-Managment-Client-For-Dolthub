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


class Dolthub:
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
                "source": {
                    "branch": pr_meta["fromBranchName"],
                    "owner": pr_meta["fromBranchOwnerName"],
                    "repo": pr_meta["fromBranchRepoName"]
                },
                "destination": {
                    "branch": pr_meta["toBranchName"],
                    "owner": pr_meta["toBranchOwnerName"],
                    "repo": pr_meta["toBranchRepoName"]
                },
                "creator": pr_meta["creatorName"],
                "fork": bool(pr_meta["isFork"])
            }

            return simple_result

        return result, status_code

    def update_pr(self, repo_owner: str, repo_name: str, pr_id: int, pr_state: str = None, pr_title: str = None, pr_message: str = None):
        """
            To update the Pull Request in question. Due to the nature of the API, everything has to be updated, even if you want to just close the PR.
            To help facilitate simple actions, the PR's existing data will be automatically pulled if an optional value is set to None.

            @param repo_owner: The owner of the repo where the PR resides. Not the submitter of the PR.
            @param repo_name: The name of the repo where the PR resides. Not the name of the fork that the PR came from.
            @param pr_id: The id of the PR as seen in the PR list of the repo.

            Optional Values - These values change the state of the PR.
            @param pr_state: Can be "Open", "Closed", or "Merged". These values are case-sensitive.
            @param pr_title: The title of the PR as seen in the PR list of the repo.
            @param pr_message: The message of the PR as seen in the PR details page. This is not a PR comment. If you want to set this as empty, use and empty string. Setting this to None will just keep the same message as before.

            @return: A tuple of the HTTP Status Code and the response body read as JSON. The response body is first and then the status code comes second.
        """

        # At least one optional argument is required, it doesn't matter which one.
        if pr_state is None and pr_title is None and pr_message is None:
            raise NeedAtLeastOneOptionalArgumentException("Specify at least one of pr_state, pr_title, or pr_message.")

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
        return result, status_code


if __name__ == "__main__":
    try:
        dolthub = Dolthub(token_file="token.txt")
        results, status_code = dolthub.update_pr(repo_owner="alexis-evelyn", repo_name="test-forking", pr_id=2, pr_title="Test PR Script", pr_state="Closed", pr_message="This is a test PR message!")
        # results = dolthub.lookup_pr(repo_owner="alexis-evelyn", repo_name="test-forking", pr_id=2)

        print(results)
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
