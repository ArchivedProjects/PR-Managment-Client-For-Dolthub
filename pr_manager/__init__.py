"""
    This Unofficial Dolthub PR Manager requires the :mod:`requests` module in order to perform HTTP Requests to the GraphQL api.

    The classes you may find important are `PRManager` and `APIServerException`.

    The List Of Classes And Their Utility Is Below.
    -----------------------------------------------
    `PRManager` - The main class and the one that performs the api operations.
    `NoAuthException` - When Authentication Fails With The GraphQL API.
    `NeedAtLeastOneOptionalArgumentException` - When At Least One Optional Argument Is Required, But It Doesn't Matter Which One
    `APIServerException` - When The GraphQL API Throws An Error.
"""

__author__ = 'Alexis Evelyn <https://twitter.com/alexisevelyn42>'
__version__ = '0.0.1'

__all__ = [
    "PRManager", "NoAuthException", "NeedAtLeastOneOptionalArgumentException", "APIServerException"
]

from pr_manager.pr_manager import PRManager, NoAuthException, NeedAtLeastOneOptionalArgumentException, APIServerException
