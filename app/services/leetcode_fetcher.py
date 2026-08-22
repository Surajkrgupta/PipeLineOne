"""Fetches LeetCode's Problem of the Day via their public GraphQL endpoint.
No auth needed -- this is the same endpoint leetcode.com's own frontend calls."""

import requests

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

POTD_QUERY = """
query questionOfToday {
  activeDailyCodingChallengeQuestion {
    date
    link
    question {
      questionId
      title
      titleSlug
      difficulty
      content
      exampleTestcases
      topicTags {
        name
      }
    }
  }
}
"""


class LeetCodeFetchError(Exception):
    pass


def fetch_potd() -> dict:
    """Returns a dict with problem_slug, title, difficulty, content (HTML),
    examples, and topic tags. Raises LeetCodeFetchError on any failure."""
    try:
        resp = requests.post(
            LEETCODE_GRAPHQL_URL,
            json={"query": POTD_QUERY, "operationName": "questionOfToday"},
            headers={"Content-Type": "application/json", "Referer": "https://leetcode.com"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()["data"]["activeDailyCodingChallengeQuestion"]
        question = data["question"]

        return {
            "problem_slug": question["titleSlug"],
            "title": question["title"],
            "difficulty": question["difficulty"],
            "content_html": question["content"],  # problem statement, contains HTML tags
            "example_testcases": question["exampleTestcases"],
            "topic_tags": [t["name"] for t in question["topicTags"]],
            "link": f"https://leetcode.com{data['link']}",
        }
    except (requests.RequestException, KeyError, ValueError) as e:
        raise LeetCodeFetchError(f"Failed to fetch LeetCode POTD: {e}") from e


if __name__ == "__main__":
    # quick manual check: python -m app.services.leetcode_fetcher
    import json
    print(json.dumps(fetch_potd(), indent=2)[:1000])
