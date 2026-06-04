#!/usr/bin/env python3
"""Post a tweet via Twitter API v2 using tweepy."""

import argparse
import os
import sys


def check_env():
    required = [
        "TWITTER_API_KEY",
        "TWITTER_API_SECRET",
        "TWITTER_ACCESS_TOKEN",
        "TWITTER_ACCESS_TOKEN_SECRET",
    ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"Error: missing environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Set them with:", file=sys.stderr)
        for v in missing:
            print(f"  export {v}='...'", file=sys.stderr)
        sys.exit(1)


def get_client():
    try:
        import tweepy
    except ImportError:
        print("Installing tweepy...", file=sys.stderr)
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tweepy", "-q", "--break-system-packages"])
        import tweepy

    return tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )


def get_v1_api():
    try:
        import tweepy
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tweepy", "-q", "--break-system-packages"])
        import tweepy

    auth = tweepy.OAuth1UserHandler(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )
    return tweepy.API(auth)


def upload_images(image_paths: list) -> list:
    """Upload up to 4 images, return list of media_ids."""
    if len(image_paths) > 4:
        print("Error: Twitter allows at most 4 images per tweet.", file=sys.stderr)
        sys.exit(1)

    api_v1 = get_v1_api()
    media_ids = []
    for path in image_paths:
        if not os.path.isfile(path):
            print(f"Error: image file not found: {path}", file=sys.stderr)
            sys.exit(1)
        print(f"Uploading image: {path}")
        media = api_v1.media_upload(path)
        media_ids.append(media.media_id)
        print(f"  Uploaded → media_id={media.media_id}")
    return media_ids


def post_one(client, text: str, reply_to: str = None, media_ids: list = None) -> str:
    """Post a single tweet and return its ID."""
    kwargs = {"text": text}
    if reply_to:
        kwargs["in_reply_to_tweet_id"] = reply_to
    if media_ids:
        kwargs["media_ids"] = media_ids
    response = client.create_tweet(**kwargs)
    return response.data["id"]


def main():
    parser = argparse.ArgumentParser(description="Post a tweet via Twitter API v2")
    parser.add_argument("--text", action="append", metavar="TEXT",
                        help="Tweet text (max 280 chars). Repeat for thread: --text t1 --text t2 --text t3")
    parser.add_argument("--reply-to", metavar="TWEET_ID", help="Tweet ID to reply to (for single tweet)")
    parser.add_argument("--image", action="append", metavar="PATH",
                        help="Image file to attach (up to 4, repeat flag for multiple)")
    args = parser.parse_args()

    if not args.text:
        print("Error: --text is required.", file=sys.stderr)
        sys.exit(1)

    for t in args.text:
        if len(t) > 280:
            print(f"Error: tweet text is {len(t)} chars, exceeds 280 char limit: {t[:40]}...", file=sys.stderr)
            sys.exit(1)

    check_env()
    client = get_client()

    # Upload images if provided (shared across first tweet or single tweet)
    media_ids = None
    if args.image:
        media_ids = upload_images(args.image)

    # --- Thread mode: multiple --text values ---
    if len(args.text) > 1:
        print(f"Posting thread ({len(args.text)} tweets)...")
        prev_id = args.reply_to  # allow thread to reply to an existing tweet
        urls = []
        for i, text in enumerate(args.text):
            # Only attach images to the first tweet of the thread
            tweet_media = media_ids if (i == 0 and media_ids) else None
            tweet_id = post_one(client, text, reply_to=prev_id, media_ids=tweet_media)
            url = f"https://twitter.com/i/web/status/{tweet_id}"
            urls.append(url)
            print(f"  [{i+1}/{len(args.text)}] Posted → {url}")
            prev_id = tweet_id
        print(f"\nThread posted successfully! {len(args.text)} tweets.")
        for i, url in enumerate(urls):
            print(f"  Tweet {i+1}: {url}")

    # --- Single tweet mode ---
    else:
        print("Posting tweet...")
        tweet_id = post_one(client, args.text[0], reply_to=args.reply_to, media_ids=media_ids)
        url = f"https://twitter.com/i/web/status/{tweet_id}"
        print(f"\nTweet posted successfully!")
        print(f"  ID:  {tweet_id}")
        print(f"  URL: {url}")


if __name__ == "__main__":
    main()
