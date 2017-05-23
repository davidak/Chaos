#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import os
import sys
import sh
import logging
import threading
import http.server
import random
import subprocess
import arrow
import settings
import patch

from os.path import dirname, abspath, join

import github_api as gh
import github_api.prs
import github_api.voting
import github_api.repos
import github_api.comments

from github_api import exceptions as gh_exc


class HTTPServerRequestHandler(http.server.BaseHTTPRequestHandler):

    def __init__(self):
        # Load fortunes
        self.fortunes = []
        with open("fortunes.txt", "r", encoding="utf8") as f:
            self.fortunes = f.read().split("\n%\n")

        # Call superclass constructor
        super(HTTPServerRequestHandler, self).__init__()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

        self.wfile.write(random.choice(self.fortunes).encode("utf8"))


def update_self_code():
    """pull the latest commits from master"""
    sh.git.pull("origin", "master")


def restart_self():
    """restart our process"""
    os.execl(sys.executable, sys.executable, *sys.argv)


def http_server():
    s = http.server.HTTPServer(('', 8080), HTTPServerRequestHandler)
    s.serve_forever()


def start_http_server():
    http_server_thread = threading.Thread(target=http_server)
    http_server_thread.start()


def install_requirements():
    """install or update requirements"""
    os.system("pip install -r requirements.txt")


def main():
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("requests").propagate = False
    logging.getLogger("sh").propagate = False

    log = logging.getLogger("chaosbot")

    api = gh.API(settings.GITHUB_USER, settings.GITHUB_SECRET)

    logging.info("starting up and entering event loop")

    os.system("pkill chaos_server")

    server_dir = join(dirname(abspath(__file__)), "server")
    subprocess.Popen([sys.executable, "server.py"], cwd=server_dir)

    log.info("starting http server")
    start_http_server()

    while True:
        log.info("looking for PRs")

        now = arrow.utcnow()
        voting_window = gh.voting.get_voting_window(now)
        prs = gh.prs.get_ready_prs(api, settings.URN, voting_window)

        needs_update = False
        for pr in prs:
            pr_num = pr["number"]
            logging.info("processing PR #%d", pr_num)

            log.info("PR %d approved for merging!", pr_num)
            try:
                gh.prs.merge_pr(api, settings.URN, pr, votes, vote_total, threshold)
            # some error, like suddenly there's a merge conflict, or some
            # new commits were introduced between findint this ready pr and
            # merging it
            except gh_exc.CouldntMerge:
                log.info("couldn't merge PR %d for some reason, skipping",
                         pr_num)
                gh.prs.label_pr(api, settings.URN, pr_num, ["can't merge"])
                continue

            gh.prs.label_pr(api, settings.URN, pr_num, ["accepted"])
            needs_update = True

        # we approved a PR, restart
        if needs_update:
            logging.info("updating code and requirements and restarting self")
            update_self_code()
            install_requirements()
            restart_self()

        logging.info("sleeping for %d seconds", settings.SLEEP_TIME)
        time.sleep(settings.SLEEP_TIME)

if __name__ == "__main__":
    main()
