from __future__ import annotations

import argparse
import dotenv
import os
import sys
import yaml
from datetime import datetime
from pathlib import Path
from urllib3.util.url import parse_url
from typing import TYPE_CHECKING

import pandas as pd

from jinja2 import Environment, FileSystemLoader
from mastodon import Mastodon
from datetime import datetime, timedelta, timezone
from scipy import stats
from statistics import median_high, median_low

from api import fetch_posts_and_boosts, reboost_toots, fetch_myposts, build_boost_file
from scorers import get_scorers, ConfiguredScorer, KeywordScorer
from thresholds import get_threshold_from_name, get_thresholds

if TYPE_CHECKING:
    from scorers import Scorer
    from thresholds import Threshold
    from argparse import Namespace, ArgumentParser


def render_digest(context: dict, output_dir: Path,  mastodon_client: Mastodon, output_type: str = "html", theme: str = "default") -> None:
    if (output_type=="html"):
        environment = Environment(
            loader=FileSystemLoader([f"templates/themes/{theme}", "templates/common"])
        )
        template = environment.get_template("index.html.jinja")
        output_html = template.render(context)
        output_file_path = output_dir / "index.html"
        output_file_path.write_text(output_html)
    elif (output_type=="bot"):
        # print("Would boost the following...")
        # print(context)
        #reboost_toots(mastodon_client, context)
        build_boost_file(mastodon_client, context)



def list_themes() -> list[str]:
    # Return themes, named by directory in `/templates/themes` and which have an `index.html.jinja` present.
    return list(
        filter(
            lambda dir_name: not dir_name.startswith(".")
            and os.path.exists(f"templates/themes/{dir_name}/index.html.jinja"),
            os.listdir("templates/themes"),
        )
    )


def format_base_url(mastodon_base_url: str) -> str:
    return mastodon_base_url.strip().rstrip("/")

def check_config_pars(pars):
    for acct_list in ["amplify_accounts"]:
        for acct in pars.get(acct_list, []):
            if len(acct.split("@")) != 2:
                sys.exit("Please provide accounts in the form 'user@host' (check failed for '%s' in list '%s')"%(acct, acct_list)) 


def add_defaults_from_config(arg_parser : ArgumentParser, config_file : Path) -> None:
    # Override defaults of parser by pars given in config file
    if config_file.exists() and config_file.is_file():
        with open(config_file, "r") as f:
            cfg_pars = yaml.safe_load(f)
        print("Loading config file '%s'"%config_file)
        check_config_pars(cfg_pars)
        arg_parser.set_defaults(**cfg_pars)

    else:
        if str(config_file) != arg_parser.get_default("config"):
            print("Couldn't load config file '%s'."%config_file)
                

def run(
    hours: int,
    scorer: Scorer,
    threshold: Threshold,
    mastodon_token: str,
    mastodon_base_url: str,
    timeline: str,
    output_dir: Path,
    output_type: str,
    theme: str,
) -> None:

    timeline_limit = 200
    myposts_limit = 1000
    # how far back to look for authors who we may repeat boost
    author_look_back_len = 10    
    # how far back to look for twitter-originated toots, which would
    # mean we don't boost another twitter-originated toot
    twitter_look_back_len = 20
    target_boosts_per_day = 15

    minutes_look_back = 20 #minutes to look back for pace

    print(f"Building digest from the past {hours} hours, maximum {timeline_limit} requests...")

    mst = Mastodon(
        user_agent="mastodon_digest_refactor",
        access_token=mastodon_token,
        api_base_url=mastodon_base_url,
    )

    # sql = sqlite3.connect('icymibotcache.db')
    # db = sql.cursor()
    # db.execute('''CREATE TABLE IF NOT EXISTS myboosts (toot_id text, toot_author_acct text, from_twitter text)''')
    # db.execute('''CREATE TABLE IF NOT EXISTS toots_seen (toot_id text, toot_author_acct text, from_twitter text, eval_score real, toot_creation text)''')
    # db.execute('''CREATE TABLE IF NOT EXISTS toots_to_boost (toot_id text, toot_author_acct text, from_twitter text, eval_score real, toot_creation text)''')
    #db.execute('''CREATE TABLE IF NOT EXISTS entries (feed_entry_id text, toot_id text, rss_feed_url text, mastodon_username text, mastodon_instance text)''')
    
    print("Still running with hardcoded filtered accounts and keywords")
    filtered_accounts = set(['EEAS@social.network.europa.eu','EU_UNGeneva@respublicae.eu', 'rmartinnielsen@mastodon.social'])

    keywords_mixedcase = ['TPNW', 'nuclear', 'missiles', 'missile', 'nonprolifwp', 'armscontrol', 'nonproliferation', 'autonomousweapons', 'killerrobots', 'SALW', 'ConferenceOnDisarmament', 'chemicalweapons', 'chemicalweapon', 'nuclearweapons', 'disarmament', 'opcw', 'landmines', 'biowarfare', 'biologicalweapons', 'ICBM', 'ICBMs']
    keywords = set([keyword.lower() for keyword in keywords_mixedcase ])
    # Algorithm description from https://icymilaw.org/about/ ; used as a basis
    # It reads its timeline for the past 24 hours.
    # 1. Fetch all the posts and boosts from our home timeline that we haven't interacted with
    posts, boosts, posts_seen = fetch_posts_and_boosts(hours, mst, timeline, timeline_limit )

    print(f"Seen {posts_seen} posts, returned {len(posts)} posts and {len(boosts)} boosts.")
    
    # Let's filter the posts and boosts here
    #
    filtered_posts = [post for post in posts
                      if (post.info['account']['acct'] not in filtered_accounts) or post.matches_keywords(keywords)]
    filtered_boosts = [post for post in boosts
                      if (post.info['account']['acct'] not in filtered_accounts) or post.matches_keywords(keywords)]
    
    most_recent_boosts = [post for post in filtered_posts
                          if (datetime.now(timezone.utc) - post.info["created_at"]) 
                            < timedelta(minutes = minutes_look_back)]
    
    myposts, myboosts, myposts_seen = fetch_myposts(24*5, mst, myposts_limit )
    print(f"In my timeline, seen {myposts_seen} posts, returned {len(myposts)} posts and {len(myboosts)} boosts.")
    # toot_id text, toot_author_acct text, from_twitter text)
    boosts_list = [{'toot_id':post.info['id'],
                    'acct':post.info['account']['acct'],
                    'from_twitter':post.from_twitter(),
                    'created_at':post.info['created_at'],
                    'link_url':post.link_urls()[0] if post.link_urls() else ''} for post in myboosts]
    myboosts_df = pd.DataFrame(boosts_list)
        
    # It reads in a list of all the posts (including boosts) it has made.
    # go back 5 days
    try:
        myoldboosts_df = pd.read_csv("icymibot_cache_myboosts.csv")
        myboosts_df = myoldboosts_df.combine_first( myboosts_df)
    except (pd.errors.EmptyDataError, IOError, OSError):
        myboosts_df.to_csv("icymibot_cache_myboosts.csv", index=False)

    boosted_authors = set(myboosts_df[-author_look_back_len:]['acct'])

    twitter_boosts = [myboosts_df[-twitter_look_back_len:]['from_twitter'] > 0.0]
    non_twitter_boosts = [myboosts_df[-twitter_look_back_len:]['from_twitter'] == 0.0]
    #non_twitter_boosts = [ post for post in myboosts[-twitter_look_back_len:] if post.from_twitter() == 0.0]

# It looks at how many reblogs and favorites each of the remaining posts have gotten and calculates a score based on their geometric mean. Note: This is only a subset of the true counts as it primarily knows what its home server (esq.social) knows. Consequently, esq.social's interactions with a post hold a special sway. This is why I decided to base a legal content aggregator on a legal-focused server. If we assume its users will more frequently interact with the target content, it ups the chances that the counts will be current. Additionally, the bot also knows the counts as they appear on mastodon.social for folks followed by @colarusso since it shares an infrastructure with @colarusso_alo. So, four communities strongly influence what the bot sees: (1) the folks it follows; (2) the folks who interact with their posts; (3) the members of esq.social who can give more insight into the actions of 2; and (4) the folks followed by Colarusso mediated by colarusso_algo who can give more insight into the actions of 2.
# It divides the score above by a number that increases with the author's follower count. That is, as the author's follower count goes up, their score goes down. As of this writing, this denominator is a sigmoid with values between 0.5 and 1, maxing out at a few thousand followers. However, I'm always fiddling with this.
# It sorts the timeline by this new score, from highest to lowest.
# It finds all the posts in the timeline that look like they came from Twitter (i.e., they include a link to twitter.com). If one of the last n boosts it has made looked like it was from Twitter, it removes all of the suspected Twitter posts from the timeline. Otherwise, it gets rid of all of the Twitter posts but the one with the highest score. As of this writing n was around 20, but I'm always playing with this value.
# It removes from the timeline posts from any author it has boosted in the last n boosts, where n again is a number subject to change but on the order of 10s.
# It makes sure it hasn't posted more than 200 times already. If it has, it stops. You may be wondering why this or some of the following tests don't come earlier, and the answer has to do with the fact that while examining and constructing the timeline the bot is collecting info it will use elsewhere regardless of whether or not it reblogs anything.
# It makes sure it's between 6 AM and and 11:30 PM US/Eastern, if it isn't it stops.
# It looks to see how many posts were made in the original timeline over the last 24 hours and the last 20 minutes. It uses these two numbers to estimate the frequency of posts it would need to make to hit a target of roughly 150 posts a day. The assumptions are such that the estimate tends to underestimate.
# It removes form the timeline all posts with a score below some multiple of the median score for available posts. Note: this can result in there not being enough posts to hit the target. Also, the multiple is always being fiddled with. See next.
# Based on this frequency it calculated above, it figures out how many boosts it should make over the next 30 min. It chooses that number of posts from the top of the timeline, if available, and tries to boost them out over the next 30 minutes. If there's an error it tries to boost a post from lower in the timeline.
    # 2. Score them, and return those that meet our threshold
    # threshold_posts = threshold.posts_meeting_criteria(posts, scorer)
    # threshold_boosts = threshold.posts_meeting_criteria(boosts, scorer)

    # 3. Sort posts and boosts by score, descending
    sorted_posts = sorted(
        filtered_posts, key = lambda post: post.get_score(scorer), reverse=True
    )
    sorted_boosts = sorted(
        filtered_boosts, key = lambda post: post.get_score(scorer), reverse=True
    )
    
    print("---posts----")
    for post in sorted_posts:
        print(post.get_score(scorer), post.content_text())
    if len(sorted_posts):
        print(median_high([post.get_score(scorer) for post in sorted_posts]))
    else:
        print("No posts")
    
    sorted_posts_drop_zeroes = sorted(
        [post for post in filtered_posts if post.get_score(scorer)>0.0],
        key = lambda post: post.get_score(scorer), reverse=True
    )
    if len(sorted_posts_drop_zeroes):
        post_median_score = median_low([post.get_score(scorer) for post in sorted_posts_drop_zeroes])
        print(f"Above median (w/o zeroes): {len(sorted_posts_drop_zeroes)} Median w/o zeroes: {post_median_score}" )
    else:
        print("No posts")

    print("---boosts----")
    for boost in sorted_boosts:
        print( boost.get_score(scorer), boost.content_text())
    if len(sorted_boosts):
        print(median_high([post.get_score(scorer) for post in sorted_boosts]))
    else:
        print("No boosts")

    sorted_boosts_drop_zeroes = sorted(
        [post for post in filtered_boosts if post.get_score(scorer)>0.0],
        key = lambda post: post.get_score(scorer), reverse=True
    )
    if len(sorted_boosts_drop_zeroes):
        print("median w/o zeroes", median_low([post.get_score(scorer) for post in sorted_boosts_drop_zeroes]))
    else:
        print("No boosts")
    
    threshold_posts = sorted(
         sorted_posts_drop_zeroes, key=lambda post: post.get_score(scorer), reverse=True
    )
    threshold_boosts = sorted(
        sorted_boosts_drop_zeroes, key=lambda post: post.get_score(scorer), reverse=True
    )
    bucket_candidates = pd.DataFrame(
        {'toot_id':post.info['id'],
                    'acct':post.info['account']['acct'],
                    'from_twitter':post.from_twitter(),
                    'created_at':post.info['created_at'],
                    'score':post.get_score(scorer),
                    'link_url':post.link_urls()[0] if post.link_urls() else ''} for post in threshold_posts
    )
    bucket_candidates_unique = bucket_candidates.groupby('acct').first()
    bucket_candidates_cream = bucket_candidates_unique[:3]
    # Now need to ...
    #  - remove duplicate links: a toot which refers to a link which the same
    #    account has already linked to doesn't need to be boosted again
    #  - maybe slow down the twitter boosting?

    # 4. Build the digest
    if len(threshold_posts) == 0 and len(threshold_boosts) == 0:
        sys.exit(
            f"No posts or boosts were found for the provided digest arguments. Exiting."
        )
    else:
        render_digest(
            context={
                "hours": hours,
                "posts": threshold_posts,
                "boosts": threshold_boosts,
                "mastodon_base_url": mastodon_base_url,
                "rendered_at": datetime.utcnow().strftime("%B %d, %Y at %H:%M:%S UTC"),
                "timeline_name": timeline,
                "threshold": threshold.get_name(),
                "scorer": scorer.get_name(),
            },
            output_dir=output_dir,
            mastodon_client=mst,
            output_type=output_type,
            theme=theme,
        )
        try:
            oldboosts_df = pd.read_csv("icymibot_cache_to_boost.csv")
            to_boost_df =oldboosts_df.combine_first(bucket_candidates_cream)
        except (pd.errors.EmptyDataError, IOError, OSError):
            print("No existing cache of items to boost")
        to_boost_df.to_csv("icymibot_cache_to_boost.csv", index=False)


if __name__ == "__main__":
    scorers = get_scorers()
    thresholds = get_thresholds()

    arg_parser = argparse.ArgumentParser(
        prog="mastodon_digest",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    arg_parser.add_argument(
        "-f",  # for "feed" since t-for-timeline is taken
        default="home",
        dest="timeline",
        help="The timeline to summarize: Expects 'home', 'local' or 'federated', or 'list:id', 'hashtag:tag'",
        required=False,
    )
    arg_parser.add_argument(
        "-n",
        choices=range(1, 25),
        default=12,
        dest="hours",
        help="The number of hours to include in the Mastodon Digest",
        type=int,
    )
    arg_parser.add_argument(
        "-s",
        choices=list(scorers.keys()),
        default="SimpleWeighted",
        dest="scorer",
        help="""Which post scoring criteria to use.
            Simple scorers take a geometric mean of boosts and favs.
            Extended scorers include reply counts in the geometric mean.
            Weighted scorers multiply the score by an inverse square root
            of the author's followers, to reduce the influence of large accounts.
        """,
    )
    arg_parser.add_argument(
        "-c", "--config",
        default="./cfg.yaml",
        dest="config",
        help="Defines a configuration file.",
        required=False,
    )
    arg_parser.add_argument(
        "-t",
        choices=list(thresholds.keys()),
        default="normal",
        dest="threshold",
        help="""Which post threshold criteria to use.
            lax = 90th percentile,
            normal = 95th percentile,
            strict = 98th percentile
        """,
    )
    arg_parser.add_argument(
        "-o",
        default="./render/",
        dest="output_dir",
        help="Output directory for the rendered digest",
        required=False,
    )
    arg_parser.add_argument(
        "--theme",
        choices=list_themes(),
        default="default",
        dest="theme",
        help="Named template theme with which to render the digest",
        required=False,
    )
    arg_parser.add_argument(
        "--output",
        choices=["html", "bot"],
        default="html",
        dest="output_type",
        help="Whether to produce an \"html\" digest (default) or boost items to a timeline (\"bot\")",
        required=False,
    )
    add_defaults_from_config(arg_parser, Path(arg_parser.parse_args().config))
    # Parse args once more with updated defaults
    args = arg_parser.parse_args()

    # Attempt to validate the output directory
    output_dir = Path(args.output_dir)
    if not output_dir.exists() or not output_dir.is_dir():
        sys.exit(f"Output directory not found: {args.output_dir}")

    # Loosely validate the timeline argument, so that if a completely unexpected string is entered,
    # we explicitly reset to 'Home', which makes the rendered output cleaner.
    timeline = args.timeline.strip().lower()
    validTimelineTypes = ["home", "local", "federated", "hashtag", "list"]
    timelineType, *_ = timeline.split(":", 1)
    if not timelineType in validTimelineTypes:
        timeline = "home"

    # load and validate env
    dotenv.load_dotenv(override=False)

    mastodon_token = os.getenv("MASTODON_TOKEN")
    print("token:", mastodon_token)
    mastodon_base_url = os.getenv("MASTODON_BASE_URL")

    if not mastodon_token:
        sys.exit("Missing environment variable: MASTODON_TOKEN")
    if not mastodon_base_url:
        sys.exit("Missing environment variable: MASTODON_BASE_URL")

    # Check if a ConfiguredScorer should be used 
    # NOTE: depends on whether the parameters in the config file require this, currently,
    #       but may be changed to always use a ConfiguredScorer as a wrapper)
    if set(vars(args)).intersection(ConfiguredScorer.get_additional_scorer_pars()):
        # At least one parameter was passed, which requires 
        # the use of a ConfiguredScorer to modify scores of the base scorer
        scorer = ConfiguredScorer(base_scorer=args.scorer, 
                                  default_host=parse_url(mastodon_base_url).hostname, 
                                  **vars(args))
    elif (args.scorer.startswith("Keyword")):
        scorer = KeywordScorer(base_scorer=args.scorer[7:],
                               **vars(args))
    else:
        scorer = scorers[args.scorer]()
        
    run(
        args.hours,
        scorer,
        get_threshold_from_name(args.threshold),
        mastodon_token,
        format_base_url(mastodon_base_url),
        timeline,
        output_dir,
        args.output_type,
        args.theme,
    )
