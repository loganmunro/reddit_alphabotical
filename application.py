import praw
import re
import json
from enum import Enum, unique
import unidecode
import string
from random import choice
from collections import OrderedDict
from psaw import PushshiftAPI
import datetime

reddit = praw.Reddit("alphabotical")

pushShift = PushshiftAPI(reddit)

fetch_time = 3  # minutes to fetch from last_fetch_time
last_fetch_time_path = "last_fetch_time.jsonl"

comment_replies_path = "comment_replies.jsonl"
banned_subreddits_path = "banned_subreddits.jsonl"

words_path = "words_clean.txt"

all_words = set(line.strip() for line in open(words_path))


@unique
class MatchType(Enum):
    alphabet_used = [ "Congratulations, your comment used all the letters in the alphabet!"]
    alphabetical_words  = [ "Congratulations, your comment's words are in alphabetical order!"]
    alphabetical_words_reverse  = [ "Congratulations, your comment's words are in reverse alphabetical order!"]


def main():

    while True:
        for comment in get_comments():
            comment_match = None

            try:
                comment_match = parse_comment(comment)
            except CommentDisqualifiedError:
                # comment didn't pass one of the checks
                pass
            if comment_match:
                print(comment.body)
                print(comment_match.name)
                print(comment.permalink)
                print("------------")
                print("gonna reply with", choice(comment_match.value))
                comment_reply(comment, comment_match)

        # store the time of the last comment parsed,
        # but if we're behind 8 mins ago, then move it up
        time = int(datetime.datetime.now().timestamp() - 8 * 60)
        time = max(comment.created_utc, time)

        with open(last_fetch_time_path, "w") as f:
            f.write(json.dumps({"last_fetch_time": int(time)}))


def parse_comment(comment):
    """Parses a praw comment and returns a MatchType enum if the comment matches one
    of the match types, otherwise None
    """

    body = comment.body
    body = unidecode.unidecode(body.lower())

    match = None

    words = wordslist(body)

    unique_words = set(words)

    # comment disqualifying rules
    ("i am a bot" not in body or
        raiser(CommentDisqualifiedError("probably a bot comment")))
    ("alpha" not in body or
        raiser(CommentDisqualifiedError("probably trying to be alphabetical")))
    (len(unique_words) >= 6 or
        raiser(CommentDisqualifiedError("requires 5 or more words")))
    (len(unique_words) / len(words) >= 0.5 or
        raiser(CommentDisqualifiedError("needs 50% unique words")))

    recognized_words = set(w for w in words if w in all_words)
    (len(recognized_words) / len(unique_words) >= 0.6 or
        raiser(CommentDisqualifiedError("require at least 60% recognized words")))
    (len("".join(words)) < 450 or
        raiser(CommentDisqualifiedError("must be fewer than 450 characters")))

    if alphabet_used(recognized_words):
        match = MatchType.alphabet_used

    wia = words_in_alphabetical(words)
    if wia:
        if wia > 0:
            match = MatchType.alphabetical_words
        elif wia < 0:
            match = MatchType.alphabetical_words_reverse

    return match


def existing_comment_reply_ids():
    pids = set(json.loads(line).get("parent_id") for line in open(comment_replies_path))
    ids = set(json.loads(line).get("id") for line in open(comment_replies_path))

    return pids.union(ids)


def comment_reply(comment, comment_match):
    if not comment or not comment_match:
        raise Exception

    d = OrderedDict()

    reply_comment = None

    tries = 0
    skip = False
    while not reply_comment and not skip:
        try:
            reply_comment = comment.reply(choice(comment_match.value))
        except Exception as e:
            tries += 1
            if tries > 2:
                skip = True
            print("Error:", str(e), comment.id +
                  ' in ' + comment.subreddit.display_name)

    if reply_comment:
        d.update({
            "parent_id": reply_comment.parent().id,
            "id": reply_comment.id,
            "submission_id": reply_comment.submission.id,
            "comment_type": comment_match.name,
            "subreddit": reply_comment.subreddit.display_name,
            "parent_author": reply_comment.parent().author.name,
            "body": reply_comment.body,
            "parent_body": reply_comment.parent().body})

        with open(comment_replies_path, "a") as f:
            f.write(json.dumps(d) + '\n')


def alphabet_used(words):
    sorted_chars = ''.join(sorted(set(''.join(words))))
    if('abcdef' not in ''.join(words) and
       'brownfox' not in ''.join(words) and
       'blackquartz' not in ''.join(words)):
        # just make sure it's not just an alphabet post
        return string.ascii_lowercase in sorted_chars


def words_in_alphabetical(words):
    '''With a list words return 1 if all words are in alphabetical order,
    -1 if in reverse otherwise None'''
    if sorted(words) == words:
        return 1
    elif sorted(words, reverse=True) == words:
        return -1


def raiser(Excep):
    raise Excep


def wordslist(body):
    # remove hyperlinks:
    body = re.sub(r'(https*:|ftps*:)[^\s]*', '', body)
    # any duplicated token we'll treat as a break
    body = re.sub(r'([^\w])\1{1,}', ' ', body)
    return [x for x in re.sub(r'[^a-z \n0-9-]', '', body).split()]


class CommentDisqualifiedError(Exception):
    """Raised if a comment failes the qualification criteria"""
    pass


def get_comments():

    with open(last_fetch_time_path) as f:
        last_fetch_time = json.loads(f.readline()).get("last_fetch_time")

    end_time = last_fetch_time + 60 * fetch_time

    banned_subreddits = set(
        json.loads(line.lower()).get("subreddit")
        for line in open(banned_subreddits_path))

    comments_list = pushShift.search_comments(
        after=last_fetch_time - 1,
        before=end_time + 1,
        sort_type='created_utc',
        sort='asc')

    existing_ids = existing_comment_reply_ids()

    for c in comments_list:

        # skip comments made in subreddits that we've been banned from
        if c.subreddit.display_name.lower() in banned_subreddits:
            continue

        # ignore already commented replies
        if c.id in existing_ids or c.parent_id in existing_ids:
            continue

        if c.author:
            if ("bot" in c.author.name.lower() or
               "auto" in c.author.name.lower()):
                continue

        yield c


if __name__ == "__main__":
    main()
