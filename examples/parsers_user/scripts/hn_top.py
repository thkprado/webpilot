"""Print the top Hacker News stories with points and comment counts. Example script: copy it to parsers_user/scripts/.

    webpilot script hn_top [-n 10]
"""
import argparse

from webpilot import Browser

ap = argparse.ArgumentParser()
ap.add_argument("-n", type=int, default=10)
args = ap.parse_args()

with Browser() as b:
    b.goto("https://news.ycombinator.com/")
    stories = b.extract()["data"]["stories"]

for s in stories[: args.n]:
    print(f"{s['points'] or 0:5} pts {s['comments']:4} comments  {s['title']}\n{'':22}{s['url']}")
