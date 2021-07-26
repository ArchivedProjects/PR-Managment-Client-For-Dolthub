from datetime import datetime

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


class NotImplementedException(Exception):
    """
        Thrown when the feature is not implemented.
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

        # Dolthub Cannot Contact AWS At The Moment If This Is Triggered
        if response.text.strip() == "upstream request timeout":
            raise APIServerException("GraphQL API Cannot Contact Upstream Right Now. Please Try Again Later!", response.text, response.status_code, response)

        # Easier To Ask For Forgiveness Than Permission Philosophy - https://docs.python.org/3.10/glossary.html#term-EAFP
        # EAFP is weird to me as I'm used to the Look Before You Leap Philosophy From Java
        # Also To Note: https://stackoverflow.com/questions/404795/lbyl-vs-eafp-in-java#comment230588_404802
        try:
            result = json.loads(response.text)
        except ValueError:
            raise APIServerException("GraphQL sent a non-JSON Response!", response.text, response.status_code, response)

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

    def delete_comment(self, comment_id: str):
        """
            Delete a comment.

            @param comment_id: The id of the comment you want to delete.

            @return: A tuple of the HTTP Status Code and the response body read as JSON. The response body is first and then the status code comes second.
        """

        graphql_query: dict = {
          "operationName": "DeletePullComment",
          "variables": {
            "_id": comment_id
          },
          "query": "mutation DeletePullComment($_id: String!) {  deletePullComment(_id: $_id) {    ...PullSummaryForPullDetails    __typename  }}fragment PullSummaryForPullDetails on PullSummary {  _id  __typename}"
        }

        result, status_code, _ = self.perform_api_operation(graphql_query=graphql_query)
        return result, status_code

    def update_comment(self, comment_id: str, message: str):
        """
            Update a comment.

            @param comment_id: The id of the comment you want to update.
            @param message: The new message to replace the existing comment with.

            @return: A tuple of the HTTP Status Code and the response body read as JSON. The response body is first and then the status code comes second.
        """

        # I would grab the author name, but I cannot look up the comment directly,
        # and don't want to burn cycles paginating for every update. So, thankfully,
        # it appears the author name doesn't change anything. Sadly I can't remove,
        # the field, otherwise I would have done so.
        graphql_query: dict = {
          "operationName": "UpdatePullComment",
          "variables": {
            "_id": comment_id,
            "authorName": "please-explain-authorName",  # Not sure what this is about, I'm not able to change the author name anyway.
            "comment": message
          },
          "query": "mutation UpdatePullComment($_id: String!, $authorName: String!, $comment: String!) {  updatePullComment(_id: $_id, authorName: $authorName, comment: $comment) {    ...PullSummaryForPullDetails    __typename  }}fragment PullSummaryForPullDetails on PullSummary {  _id  __typename}"
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

            @return: Information about the PR created and if simple mode is turned off, also the HTTP status code.
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

    def list_prs(self, repo_owner: str, repo_name: str, page_token: str = None, simple: bool = True):
        """
            List PRs for a repo.

            @param repo_owner: The owner of the repo you want to list the PRs for.
            @param repo_name: The name of the repo you want to list the PRs for.

            Optional Values
            @param page_token: The page token you want to start with (untested).
            @param simple: Boolean that defaults to True in order to provide a consistent and simple dictionary that'll remain the same even when the API changes. Changing this value to False will return the raw API body as a dictionary.

            @return: The list of PRs and if simple mode is turned off, also the HTTP status code.
        """

        graphql_query: dict = {
          "operationName": "PullsForRepo",
          "variables": {
            "ownerName": repo_owner,
            "repoName": repo_name
          },
          "query": "query PullsForRepo($ownerName: String!, $repoName: String!, $pageToken: String) {  pulls(ownerName: $ownerName, repoName: $repoName, pageToken: $pageToken) {    ...PullListForPullList    __typename  }}fragment PullListForPullList on PullList {  list {    ...PullForPullList    __typename  }  nextPageToken  __typename}fragment PullForPullList on Pull {  _id  createdAt  ownerName  repoName  pullId  creatorName  description  state  title  __typename}"
        }

        # Allows the Caller To Start From A Specific Page
        if page_token is not None:
            graphql_query["variables"]["pageToken"] = page_token

        has_next_page: bool = True
        while has_next_page:
            result, status_code, _ = self.perform_api_operation(graphql_query=graphql_query)

            # Check For Next Page Token If Any, Otherwise Set The Loop To Close
            if "nextPageToken" not in result["data"]["pulls"] or result["data"]["pulls"]["nextPageToken"].strip() == "":
                has_next_page: bool = False
            else:
                graphql_query["variables"]["pageToken"] = result["data"]["pulls"]["nextPageToken"]

            if simple:
                pr_list: list = result["data"]["pulls"]["list"]

                # More than One PR is likely to be in this list
                # As this is supposed to be simple mode, we take out the need
                # for the caller to have to use a for loop inside a for loop.
                for pr in pr_list:
                    simple_result: dict = {
                        "id": int(pr["pullId"]),
                        "state": pr["state"],
                        "title": pr["title"],
                        "message": pr["description"],
                        "creator": pr["creatorName"],
                        "creation_date_unix": pr["createdAt"],

                        # The divide over 1000 is to convert the timestamp to
                        # a format that Python can understand.
                        "creation_date": datetime.fromtimestamp(pr["createdAt"]/1000.0),
                        "owner": pr["ownerName"],
                        "repo": pr["repoName"]
                    }

                    yield simple_result
            else:
                yield result, status_code

    def list_pr_change_log(self, repo_owner: str, repo_name: str, pr_id: int, page_token: str = None, simple: bool = True):
        """
            List The Changes To Requested PR

            @param repo_owner: The owner of the repo you want to list the PRs for.
            @param repo_name: The name of the repo you want to list the PRs for.
            @param pr_id: The id of the PR as seen in the PR list of the repo.

            Optional Values
            @param page_token: The page token you want to start with (not implemented due to pagination not existing for this api).
            @param simple: Boolean that defaults to True in order to provide a consistent and simple dictionary that'll remain the same even when the API changes. Changing this value to False will return the raw API body as a dictionary.

            @return: The list of changes to the PR and if simple mode is turned off, also the HTTP status code.
        """

        graphql_query: dict = {
          "operationName": "PullDetailsForPullDetails",
          "variables": {
            "ownerName": repo_owner,
            "repoName": repo_name,
            "pullId": str(pr_id)
          },
          "query": "query PullDetailsForPullDetails($repoName: String!, $ownerName: String!, $pullId: String!) {  pull(repoName: $repoName, ownerName: $ownerName, pullId: $pullId) {    ...PullDetails    __typename  }}fragment PullDetails on Pull {  _id  fromBranchName  toBranchName  details {    ...PullDetailsForPullDetails    __typename  }  __typename}fragment PullDetailsForPullDetails on PullDetails {  ... on PullDetailComment {    ...PullDetailComment    __typename  }  ... on PullDetailCommit {    ...PullDetailCommit    __typename  }  ... on PullDetailSummary {    ...PullDetailSummary    __typename  }  ... on PullDetailLog {    ...PullDetailLog    __typename  }  __typename}fragment PullDetailComment on PullDetailComment {  _id  authorName  comment  createdAt  updatedAt  __typename}fragment PullDetailCommit on PullDetailCommit {  _id  username  message  createdAt  commitId  parentCommitId  __typename}fragment PullDetailSummary on PullDetailSummary {  _id  username  createdAt  numCommits  __typename}fragment PullDetailLog on PullDetailLog {  _id  username  createdAt  activity  __typename}"
        }

        result, status_code, _ = self.perform_api_operation(graphql_query=graphql_query)
        if simple:
            # We Paginate The Log For The Caller And Standardize The Format Too If Simple Mode Is On
            log_entries: list = result["data"]["pull"]["details"]

            entry_types: dict = {
                "PullDetailComment": "Comment",
                "PullDetailCommit": "Commit",
                "PullDetailSummary": "Summary",
                "PullDetailLog": "Log"
            }

            # We can only have Comment, Commit, Summary, and Log as our types
            for entry in log_entries:
                # Comment - authorName, comment, updatedAt
                # Commit - username, message, commitId, parentCommitId
                # Summary - username, numCommits
                # Log - username, activity

                simple_result: dict = {
                    "id": entry["_id"],
                    "type": entry_types[entry["__typename"]] if entry["__typename"] in entry_types else entry["__typename"],  # Future Proofing For New Types
                    "creation_date_unix": entry["createdAt"],
                    "creation_date": datetime.fromtimestamp(entry["createdAt"]/1000.0)
                }

                # Add In Entry Type Specific Metadata
                # Would Be Nice: https://docs.python.org/3.10/whatsnew/3.10.html#pep-634-structural-pattern-matching
                if simple_result["type"] == "Comment":
                    simple_result["user"] = entry["authorName"]
                    simple_result["updated_date_unix"] = entry["updatedAt"]
                    simple_result["updated_date"] = datetime.fromtimestamp(entry["updatedAt"]/1000.0)
                    simple_result["message"] = entry["comment"]
                elif simple_result["type"] == "Commit":
                    simple_result["user"] = entry["username"]
                    simple_result["message"] = entry["message"]
                    simple_result["current_commit_id"] = entry["commitId"]
                    simple_result["previous_commit_id"] = entry["parentCommitId"]
                elif simple_result["type"] == "Summary":
                    simple_result["user"] = entry["username"]
                    simple_result["commits"] = entry["numCommits"]
                elif simple_result["type"] == "Log":
                    simple_result["user"] = entry["username"]
                    simple_result["state"] = entry["activity"]

                yield simple_result
        else:
            # Just Return The Raw API Response If Simple Mode Is Off
            # This is set to yield incase pagination is added to this api call in the future
            yield result, status_code

    def pull_pr_diff_summary(self, source_repo_owner: str, source_repo_name: str, source_commit_id: str, destination_repo_owner: str, destination_repo_name: str, destination_commit_id: str, simple: bool = True):
        """
            Retrieves the summary of changes the PR makes. This list will stay the same even after merge assuming the same commit ids are supplied.

            @param source_repo_owner: The owner of the repo the PR is coming from.
            @param source_repo_name: The name of the repo the PR is coming from.
            @param source_commit_id: The commit id of the latest commit in the PR.

            @param destination_repo_owner: The owner of the repo the PR is merging into.
            @param destination_repo_name: The name of the repo the PR is merging into.
            @param destination_commit_id: The commit id of the commit the PR is merging into.

            Optional Values
            @param simple: Boolean that defaults to True in order to provide a consistent and simple dictionary that'll remain the same even when the API changes. Changing this value to False will return the raw API body as a dictionary.

            @return: The summary of changes the PR makes and if simple mode is turned off, also the HTTP status code.
        """

        graphql_query: dict = {
          "operationName": "DiffSummaryAsync",
          "variables": {
            "initialReq": {
              "fromRepoName": destination_repo_name,
              "fromOwnerName": destination_repo_owner,
              "toRepoName": source_repo_name,
              "toOwnerName": source_repo_owner,
              "fromCommitId": destination_commit_id,
              "toCommitId": source_commit_id
            }
          },
          "query": "query DiffSummaryAsync($initialReq: DiffSummaryReq, $resolvedReq: ResolvedDiffSummaryReq) {  diffSummaryAsync(initialReq: $initialReq, resolvedReq: $resolvedReq) {    resolvedReq {      fromCommitName      toCommitName      tableName      __typename    }    diffSummary {      ...DiffSummaryForDiffs      __typename    }    __typename  }}fragment DiffSummaryForDiffs on DiffSummary {  rowsUnmodified  rowsAdded  rowsDeleted  rowsModified  cellsModified  rowCount  cellCount  __typename}"
        }

        result, status_code, _ = self.perform_api_operation(graphql_query=graphql_query)
        if simple:
            summary = result["data"]["diffSummaryAsync"]["diffSummary"]

            simple_result: dict = {
                "rows": {
                    "count": summary["rowCount"],
                    "modified": summary["rowsModified"],
                    "unmodified": summary["rowsUnmodified"],  # Functionally, this is rowCount-rowsModified.
                    "added": summary["rowsAdded"],
                    "deleted": summary["rowsDeleted"]
                },
                "cells": {
                    "count": summary["cellCount"],
                    "modified": summary["cellsModified"],
                    "unmodified": summary["cellCount"]-summary["cellsModified"]  # Would be cellsUnmodified if the key existed.

                    # There's no way for me to know this information without
                    #   pulling all the data for both master and the PR
                    # "added": summary["cellsAdded"],
                    # "deleted": summary["cellsDeleted"]
                }
            }

            return simple_result

        return result, status_code

    def pull_pr_diff(self, repo_owner: str, repo_name: str, pr_id: int, table_name: str = None, page_token: str = None, simple: bool = True):
        """
            Not Fully Implemented Yet...

            The list of changes the PR makes.

            *Currently shows row additions, row deletions, and indirectly, row modifications.
            This does not show schema changes at the moment.*

            Due to the complexity of working with a separate page token per table, non-simple mode is disabled right now.
            So, the variable, simple, must be True else a NotImplementedException will be thrown.
            Also, table_name is currently required as only simple mode can be used at the moment.

            @param repo_owner: The owner of the repo where the PR resides. Not the submitter of the PR.
            @param repo_name: The name of the repo where the PR resides. Not the name of the fork that the PR came from.
            @param pr_id: The id of the PR as seen in the PR list of the repo.
            @param table_name: The name of the table to lookup the diff for. This variable is case sensitive.

            Optional Values
            @param page_token: The page token you want to start with (untested).

            @return: Information about the PR requested and if simple mode is turned off, also the HTTP status code.
        """

        # If a table is not specified, we aren't returning anything (when simple mode is on)
        # If simple mode is off, then the user has to deal with everything themselves
        if not isinstance(table_name, str) and simple:
            # I currently only return one table's diff to make life a lot simpler in simple mode,
            #   that and I have yet to determine exactly how pagination works with multiple separate pagination tokens, one for each table.
            # More info can be seen in the comment wall where non-simple mode pagination is supposed to occur.
            raise NeedAtLeastOneOptionalArgumentException("The table_name argument is required for simple mode. Please specify the name of the table you want to view the diff for as a string. The variable is case sensitive.")

        graphql_query: dict = {
          "operationName": "PullDiffForTableList",
          "variables": {
            "ownerName": repo_owner,
            "repoName": repo_name,
            "pullId": str(pr_id)
          },
          "query": "query PullDiffForTableList($ownerName: String!, $repoName: String!, $pullId: String!) {  pullCommitDiff(repoName: $repoName, ownerName: $ownerName, pullId: $pullId) {    ...CommitDiffForTableList    __typename  }}fragment CommitDiffForTableList on CommitDiff {  _id  toOwnerName  toRepoName  toCommitId  fromOwnerName  fromRepoName  fromCommitId  tableDiffs {    ...TableDiffForTableList    __typename  }  __typename}fragment TableDiffForTableList on TableDiff {  oldTable {    ...TableForDiffTableList    __typename  }  newTable {    ...TableForDiffTableList    __typename  }  numChangedSchemas  rowDiffColumns {    ...ColumnForDiffTableList    __typename  }  rowDiffs {    ...RowDiffListForTableList    __typename  }  schemaDiff {    ...SchemaDiffForTableList    __typename  }  schemaPatch  __typename}fragment TableForDiffTableList on Table {  tableName  columns {    ...ColumnForDiffTableList    __typename  }  __typename}fragment ColumnForDiffTableList on Column {  name  isPrimaryKey  type  maxLength  constraints {    notNull    __typename  }  __typename}fragment RowDiffListForTableList on RowDiffList {  list {    ...RowDiffForTableList    __typename  }  nextPageToken  filterByRowTypeRequest {    pageToken    filterByRowType    __typename  }  __typename}fragment RowDiffForTableList on RowDiff {  added {    ...RowForTableList    __typename  }  deleted {    ...RowForTableList    __typename  }  __typename}fragment RowForTableList on Row {  columnValues {    ...ColumnValueForTableList    __typename  }  __typename}fragment ColumnValueForTableList on ColumnValue {  displayValue  __typename}fragment SchemaDiffForTableList on TextDiff {  leftLines {    ...SchemaDiffLineForTableList    __typename  }  rightLines {    ...SchemaDiffLineForTableList    __typename  }  __typename}fragment SchemaDiffLineForTableList on Line {  content  lineNumber  type  __typename}"
        }

        # Allows the Caller To Start From A Specific Page
        if page_token is not None:
            graphql_query["variables"]["pageToken"] = page_token

        has_next_page: bool = True
        while has_next_page:
            result, status_code, _ = self.perform_api_operation(graphql_query=graphql_query)

            if simple:
                pr_meta = result["data"]["pullCommitDiff"]

                desired_table_index: int = -1
                for table in pr_meta["tableDiffs"]:
                    # We Favor New Table Over Old Table As That's New Data
                    current_table_name: str = ""
                    if isinstance(table["newTable"], dict) and "tableName" in table["newTable"]:
                        current_table_name: str = table["newTable"]["tableName"]
                    elif isinstance(table["oldTable"], dict) and "tableName" in table["oldTable"]:
                        current_table_name: str = table["oldTable"]["tableName"]

                    if current_table_name.strip().lower() == table_name.strip().lower():
                        desired_table_index: int = pr_meta["tableDiffs"].index(table)
                        break

                # If no such table is found, then we just return
                if desired_table_index == -1:
                    return

                # Check For Next Page Token If Any, Otherwise Set The Loop To Close
                # We only return one table at a time as it's so much simpler than handling a lot of tables with their own paginations tokens at once
                if "nextPageToken" not in pr_meta["tableDiffs"][desired_table_index]["rowDiffs"] or pr_meta["tableDiffs"][desired_table_index]["rowDiffs"]["nextPageToken"].strip() == "":
                    has_next_page: bool = False
                else:
                    graphql_query["variables"]["pageToken"] = pr_meta["tableDiffs"][desired_table_index]["rowDiffs"]["nextPageToken"]

                table_meta = pr_meta["tableDiffs"][desired_table_index]
                table_columns = table_meta["rowDiffColumns"]
                table_rows = table_meta["rowDiffs"]["list"]

                # Turn Column List Into Simple List
                columns_list = []
                for column in table_columns:
                    columns_list.append(column["name"])

                for row in table_rows:
                    added_row = row["added"]["columnValues"] if isinstance(row["added"], dict) and "columnValues" in row["added"] else None
                    deleted_row = row["deleted"]["columnValues"] if isinstance(row["deleted"], dict) and "columnValues" in row["deleted"] else None

                    added_row_simple = {}
                    if added_row is not None:
                        counter: int = 0
                        for column in added_row:
                            name = columns_list[counter]
                            value = column["displayValue"]

                            added_row_simple[name] = value
                            counter += 1

                    deleted_row_simple = {}
                    if deleted_row is not None:
                        counter: int = 0
                        for column in deleted_row:
                            name = columns_list[counter]
                            value = column["displayValue"]

                            deleted_row_simple[name] = value
                            counter += 1

                    # Check If Dictionaries are Empty To Set To None
                    if not added_row_simple:
                        added_row_simple = None

                    if not deleted_row_simple:
                        deleted_row_simple = None

                    simple_result: dict = {
                        "added": added_row_simple,
                        "deleted": deleted_row_simple,

                        # These exist to make your life a lot easier
                        "source_repo_owner": pr_meta["toOwnerName"],
                        "source_repo_name": pr_meta["toRepoName"],
                        "source_commit_id": pr_meta["toCommitId"],
                        "destination_repo_owner": pr_meta["fromOwnerName"],
                        "destination_repo_name": pr_meta["fromRepoName"],
                        "destination_commit_id": pr_meta["fromCommitId"]
                    }

                    yield simple_result
            else:
                # The reason for this not being implemented is because every table the repo has can have a separate pagination token.
                # I have yet to determine which tokens to use to get all the data in as few requests as possible.
                # I suspect I can either go with the table with the longest diff or just loop through until I run out of tokens.
                # However, I want to setup tests before I implement multi-table pagination.
                raise NotImplementedException("Currently, only simple mode is implemented for this function, if you would like to parse the api response from GraphQL directly, please use the function, perform_api_operation, to perform the operation.")
                # yield result, status_code


if __name__ == "__main__":
    """
        The main function is purely meant for demonstration purposes and should be disregarded for any practical purposes.
    """

    try:
        manager = PRManager(token_file="token.txt")

        # Update Comment Demo
        # manager.update_comment(comment_id="repositoryOwners/alexis-evelyn/repositories/test-forking/pulls/6/comments/cbda83a6-c46c-4a64-ad32-58d8a22ae476", message="Automated Comment Update #3")

        # List Comments With Creation Date Demo
        # for entry in manager.list_pr_change_log(repo_owner="alexis-evelyn", repo_name="test-forking", pr_id=6):
        #     if entry["type"] == "Comment":
        #         print(entry["message"], entry["creation_date"])
        #         print(json.dumps(entry, default=str))

        # Batch Delete Comments Demo
        # for entry in manager.list_pr_change_log(repo_owner="alexis-evelyn", repo_name="test-forking", pr_id=5):
        #     if entry["type"] == "Comment" and "This is an automated comment to force pagination for the PR" in entry["message"] and entry["user"] == "alexis-evelyn":
        #         print(f"Deleting Comment With Message: {entry['message']}!!!")
        #         manager.delete_comment(comment_id=entry["id"])

        # List PRs Demo
        # pr_list = manager.list_prs(repo_owner="dolthub", repo_name="logo-2k-extended")
        # for pr in pr_list:
        #     print(json.dumps(pr, default=str))

        # Update PR Demos
        # results, status_code = manager.update_pr(repo_owner="alexis-evelyn", repo_name="test-forking", pr_id=6, pr_state="Open")
        # results, status_code, merged_results, merged_status_code = manager.update_pr(repo_owner="alexis-evelyn", repo_name="test-forking", pr_id=3, pr_state="Merged")

        # Create and Then Lookup PR Demo
        # create_pr_result = manager.create_pr(source_repo_owner="alexis-evelyn", source_repo_name="test-forking", source_branch="test_pr_script_6",
        #                                      destination_repo_owner="alexis-evelyn", destination_repo_name="test-forking", destination_branch="master")
        # lookup_pr_results = manager.lookup_pr(repo_owner="alexis-evelyn", repo_name="test-forking", pr_id=create_pr_result["id"])
        #
        # print(f"Create PR Result: {create_pr_result}")
        # print(f"Lookup PR Result: {lookup_pr_results}")

        # Merge PR Demo
        # results, status_code = manager.merge_pr(repo_owner="alexis-evelyn", repo_name="test-forking", pr_id=7)

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
    except NotImplementedException as e:
        print(f"NotImplementedException: {e}")
    except APIServerException as e:
        message, result, status_code, response = e.args

        if isinstance(result, dict) and "errors" in result:
            for error in result["errors"]:
                if "message" in error:
                    print(f"APIServerException: {message} - {error['message']}")
        else:
            print(f"APIServerException: {message} - Status Code: {status_code}")
