from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import pandas as pd

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
    

def fetch_posts_and_boosts(
    hours: int, mastodon_client: Mastodon, timeline: str, timeline_limit: int = 1000
) -> tuple[list[ScoredPost], list[ScoredPost], int]:
    """Fetches posts from the home timeline that the account hasn't interacted with"""

    #TIMELINE_LIMIT = 1000  # Should this be documented? Configurable?

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

    # Based on icymilaw.org/about
    # It removes all posts from the timeline:
    # [x] authored by anyone with the #nobot or #noindex tag in their bio;
    # [x] originally posted more than 24 hours ago (i.e., boosts of content authored more than 24 hours ago);
    # [ ] made by folks it doesn't follow (i.e., boosts made by folks it follows of folks it doesn't); OR
    # [x] it has already boosted;

    # Iterate over our timeline until we run out of posts or we hit the limit
    while response and total_posts_seen <= timeline_limit:

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
                    and (datetime.now(timezone.utc) - scored_post.info["created_at"]) < timedelta(hours = hours)
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

    return posts, boosts, total_posts_seen


def fetch_myposts(
    hours: int, mastodon_client: Mastodon, timeline_limit: int = 1000
) -> tuple[list[ScoredPost], list[ScoredPost], int]:
    """Fetches posts from the home timeline that the account hasn't interacted with"""

    #TIMELINE_LIMIT = 1000  # Should this be documented? Configurable?

    # First, get our filters
    filters = mastodon_client.filters()

    # Set our start query
    start = datetime.now(timezone.utc) - timedelta(hours=hours)

    posts = []
    boosts = []
    seen_post_urls = set()
    total_posts_seen = 0

    mastodon_acct = mastodon_client.me()['acct'].strip().lower()
    response = mastodon_client.account_statuses(mastodon_client.me()['id'], min_id=start)

    while response and total_posts_seen <= timeline_limit:
        for post in response:
            total_posts_seen += 1

            boost = False
            if post["reblog"] is not None:
                post = post["reblog"]  # look at the boosted post
                boost = True

            scored_post = ScoredPost(post)  # wrap the post data as a ScoredPost
            if (datetime.now(timezone.utc) - scored_post.info["created_at"]) < timedelta(hours = hours):
                # Append to either the boosts list or the posts lists
                if boost:
                    boosts.append(scored_post)
                else:
                    posts.append(scored_post)
                seen_post_urls.add(scored_post.url)
        response = mastodon_client.fetch_previous(
            response
        )  # fetch the previous (because of reverse chron) page of results

    return posts, boosts, total_posts_seen


def reboost_toots(mastodon_client: Mastodon, context: dict) -> None:
    """Boosts toots provided in the context"""
    # This could eventually also issue a summary toot
    for scored_post in context['posts']:
        print (f"url: {scored_post.url}")
        status = mastodon_client.status(scored_post.info['id'])
        #print (status.content)
        print (f"WOULD Calling mastodon_client.reblog({scored_post.info['id']}, visibility='unlisted')")
#        mastodon_client.status_reblog(scored_post.info['id'], visibility='unlisted')

def build_boost_file(mastodon_client: Mastodon, context: dict) -> None:
    """Writes a file of toots to be boosted, as provided in the context"""
    # This could eventually also issue a summary toot
    to_boost_df = pd.DataFrame(
        [{'toot_id':post.info['id'],
            'acct':post.info['account']['acct'],
            'from_twitter':post.from_twitter(),
            'created_at':post.info['created_at'],
            'link_url':post.link_urls()[0] if post.link_urls() else ''} for post in context['posts']]
    )
    try:
        oldboosts_df = pd.read_csv("icymibot_cache_to_boost.csv")
        to_boost_df =oldboosts_df.combine_first(to_boost_df)
    except (pd.errors.EmptyDataError, IOError, OSError):
        print("No existing cache of items to boost")
    
    to_boost_df.to_csv("icymibot_cache_to_boost.csv", index=False)

def boost_toot_from_file(mastodon_client: Mastodon, bucket_filename: str) -> None:
    try:
        to_boost_df = pd.read_csv(bucket_filename)
    except (pd.errors.EmptyDataError, IOError, OSError):
        print("No existing cache of items to boost")
        return
    if len(to_boost_df)==0:
        print("No additional toots to boost")
        return
    print(f"Would boost {to_boost_df.loc[0]['toot_id']} (from {to_boost_df.loc[0]['acct']})")
    mastodon_client.status_reblog(to_boost_df.loc[0]['toot_id'], visibility="unlisted")
    to_boost_df = to_boost_df[1:]
    to_boost_df.to_csv(bucket_filename, index=False)
    

    # for scored_post in context['posts']:
    #     print (f"url: {scored_post.url}")
    #     status = mastodon_client.status(scored_post.info['id'])
    #     #print (status.content)
    #     print (f"WOULD Calling mastodon_client.reblog({scored_post.info['id']}, visibility='unlisted')")
#        mastodon_client.status_reblog(scored_post.info['id'], visibility='unlisted')
