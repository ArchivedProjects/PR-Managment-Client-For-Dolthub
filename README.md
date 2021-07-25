# Unofficial PR Manager For Dolthub

### Implemented Features

1. Creating Pull Requests
2. Listing Pull Requests on Repositories
3. Looking Up Pull Request Details
4. Updating Pull Request Details
5. Merging Pull Requests
6. Listing Pull Request Change Logs
7. Commenting on Pull Requests
8. Updating Comments
9. Deleting Comments
10. Sending GraphQL Queries As Dictionaries Directly

I should note, PR changelogs include listing comments, merge status, closing status, opening status, newly added commits, and the summary of the changes to the PR.

In order to use the PR Manager, you'll have to import PRManager and you'll also want to at least handle APIServerException. APIServerException is thrown whenever Dolthub's API throws an exception.

I should also mention, the authentication token is just the value of the cookie, dolthubToken. You can either create a text file with the contents of the cookie in it or just feed the cookie in directly. If your cookie looks like `dolthubToken=abc123;`, you'd want to just put `abc123` in your file or feed it in as a variable. Newlines don't matter in the file as I've had plenty of experiences with editors that just have to have the newline in the file, so I strip them out for you. The purpose of the file method is so you don't have to hardcode the cookie into your script and I make it as easy as possible by reading in the file for you so all you need to do is pass in the filepath if you use the file method.

As the public api does not yet support authenticated actions, the private api is the only way to manage PRs automatically, so I currently use the private api to perform requests (which the Dolthub team knows about as we are using it for the menus bounty). I decided to create this Python module to help make a decent solution for submitting PRs automatically without hackish solutions or the learning curve that comes with reverse engineering an api.

Below is a simple example to list the PRs for a previous bounty on Dolthub.

```Python
from pr_manager import PRManager

manager = PRManager(token_file="token.txt")
for pr in manager.list_prs(repo_owner="dolthub", repo_name="logo-2k-extended"):
    print(f"{pr['id']} - {pr['state']} - {pr['title']} - {pr['creator']} - {pr['creation_date']}")
```

There are quite a few examples in the pr_manager.py script that I left in the section that checks if the script is the main file running (at the bottom of the script). I have tested all of the examples I listed in that section before submitting them to be committed.
