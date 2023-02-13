from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from models import ScoredPost

if TYPE_CHECKING:
    from mastodon import Mastodon


def get_full_account_name(acct : str, default_host : str) -> str:
    """
    Adds the default hostname to the user name if not present
    """
    if acct == "":
        return ""
    if len(acct.split("@")) == 2:
        return acct
    else:
        return "@".join((acct, default_host))

# Copied from https://github.com/halcy/Mastodon.py/issues/309
# Code by @BackSeat (Keith Edmunds)
#@api_version("4.0.0", "4.0.0", _DICT_VERSION_ACCOUNT)
def tag_following(mastodon_client: Mastodon , max_id=None, min_id=None, since_id=None, limit=None):
    """
    Fetch tags the given user is following.

    Returns a list of tags dicts
    """
    if max_id is not None:
        max_id = mastodon_client.__unpack_id(max_id, dateconv=True)

    if min_id is not None:
        min_id = mastodon_client.__unpack_id(min_id, dateconv=True)

    if since_id is not None:
        since_id = mastodon_client.__unpack_id(since_id, dateconv=True)

    params = mastodon_client.__generate_params(locals(), ['id'])
    url = '/api/v1/followed_tags'
    return mastodon_client.__api_request('GET', url, params)

def get_followed_hashtags( mastodon_client: Mastodon ) -> list[String]:
     """Give a list of followed hashtags"""
     return tag_following(mastodon_client)


def fetch_posts_and_boosts(
    hours: int, mastodon_client: Mastodon, timeline: str
) -> tuple[list[ScoredPost], list[ScoredPost]]:
    """Fetches posts from the home timeline that the account hasn't interacted with"""

    TIMELINE_LIMIT = 1000  # Should this be documented? Configurable?

    # First, get our filters
    filters = mastodon_client.filters()

    # Set our start query
    start = datetime.now(timezone.utc) - timedelta(hours=hours)

    posts = []
    boosts = []
    seen_post_urls = set()
    total_posts_seen = 0

    # If timeline name is specified as hashtag:tagName or list:list-name, look-up with those names,
    # else accept 'federated' and 'local' to process from the server public and local timelines.
    #
    # We default to 'home' if the name is unrecognized
    if ":" in timeline:
        timelineType, timelineId = timeline.lower().split(":", 1)
    else:
        timelineType = timeline.lower()

    if timelineType == "hashtag":
        response = mastodon_client.timeline_hashtag(timelineId, min_id=start)
    elif timelineType == "list":
        if not timelineId.isnumeric():
            raise TypeError('Cannot load list timeline: ID must be numeric, e.g.: https://example.social/lists/4 would be list:4')

        response = mastodon_client.timeline_list(timelineId, min_id=start)
    elif timelineType == "federated":
        response = mastodon_client.timeline_public(min_id=start)
    elif timelineType == "local":
        response = mastodon_client.timeline_local(min_id=start)
    else:
        response = mastodon_client.timeline(min_id=start)

    mastodon_acct = mastodon_client.me()['acct'].strip().lower()

    # Iterate over our timeline until we run out of posts or we hit the limit
    while response and total_posts_seen < TIMELINE_LIMIT:

        # Apply our server-side filters
        if filters:
            filtered_response = mastodon_client.filters_apply(response, filters, "home")
        else:
            filtered_response = response

        for post in filtered_response:
            total_posts_seen += 1

            boost = False
            if post["reblog"] is not None:
                post = post["reblog"]  # look at the boosted post
                boost = True

            scored_post = ScoredPost(post)  # wrap the post data as a ScoredPost

            if scored_post.url not in seen_post_urls:
                # Apply our local filters
                # Basically ignore my posts or posts I've interacted with
                # and ignore posts from accounts that have "#noindex" or "#nobot"
                if (
                    not scored_post.info["reblogged"]
                    and not scored_post.info["favourited"]
                    and not scored_post.info["bookmarked"]
                    and scored_post.info["account"]["acct"].strip().lower() != mastodon_acct
                    and "#noindex" not in scored_post.info["account"]["note"].lower()
                    and "#nobot" not in scored_post.info["account"]["note"].lower()
                ):
                    # Append to either the boosts list or the posts lists
                    if boost:
                        boosts.append(scored_post)
                    else:
                        posts.append(scored_post)
                    seen_post_urls.add(scored_post.url)

        response = mastodon_client.fetch_previous(
            response
        )  # fetch the previous (because of reverse chron) page of results

    return posts, boosts

def reboost_toots(mastodon_client: Mastodon, context: dict) -> None:
    """Boosts toots provided in the context"""
    # This could eventually also issue a summary toot
    for scored_post in context['posts']:
        print (f"url: {scored_post.url}")
        status = mastodon_client.status(scored_post.info['id'])
        #print (status.content)
        print (f"Calling mastodon_client.reblog({scored_post.info['id']}, visibility='unlisted')")
        mastodon_client.status_reblog(scored_post.info['id'], visibility='unlisted')
