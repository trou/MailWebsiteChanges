#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright: (2013-2017) Michael Till Beck <Debianguru@gmx.de>
# License: GPL-2.0+

#test

import argparse
import io
from lxml import etree
import hashlib

import smtplib
from email.mime.text import MIMEText
from email.header import Header
from urllib.parse import urljoin

import os
import sys
import getopt
import traceback

import time
from time import strftime
import random

import importlib
import logging
import difflib
from pathlib import Path

config = None

defaultEncoding = 'utf-8'

# this is how an empty RSS feed looks like
emptyfeed = """<?xml version="1.0"?>
<rss version="2.0">
 <channel>
  <title>MailWebsiteChanges Feed</title>
  <link>https://github.com/mtill/MailWebsiteChanges</link>
  <description>MailWebsiteChanges Feed</description>
 </channel>
</rss>"""

mailsession = None

# Setup logger
logger = logging.getLogger("mwc")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# generates a new RSS feed item
def genFeedItem(subject, content, link, change):
    feeditem = etree.Element('item')
    titleitem = etree.Element('title')
    titleitem.text = subject + ' #' + str(change)
    feeditem.append(titleitem)
    linkitem = etree.Element('link')
    linkitem.text = link
    feeditem.append(linkitem)
    descriptionitem = etree.Element('description')
    descriptionitem.text = content
    feeditem.append(descriptionitem)
    guiditem = etree.Element('guid')
    guiditem.text = str(random.getrandbits(32))
    feeditem.append(guiditem)
    dateitem = etree.Element('pubDate')
    dateitem.text = strftime("%a, %d %b %Y %H:%M:%S %Z", time.localtime())
    feeditem.append(dateitem)

    return feeditem


# sends mail notification
def sendmail(receivers, subject, content, sendAsHtml, link, encoding=None):
    global mailsession, defaultEncoding

    if encoding is None:
        encoding = defaultEncoding

    if sendAsHtml:
        baseurl = None
        if link is not None:
            content = '<p><a href="' + link + '">' + subject + '</a></p>\n' + content
            baseurl = urljoin(link, '/')
        mail = MIMEText('<html><head><title>' + subject + '</title>' + ('<base href="' + baseurl + '">' if baseurl else '') + '</head><body>' + content + '</body></html>', 'html', encoding)
    else:
        if link is not None:
            content = link + '\n\n' + content
        mail = MIMEText(content, 'plain', encoding)

    mail['From'] = config.sender
    mail['To'] = ", ".join(receivers)
    mail['Subject'] = Header(subject, encoding)

    # initialize session once, not each time this method gets called
    if mailsession is None:
        mailsession = smtplib.SMTP(config.smtphost, config.smtpport)
        if config.useTLS:
            mailsession.ehlo()
            mailsession.starttls()
        if config.smtpusername is not None:
            mailsession.login(config.smtpusername, config.smtppwd)

    mailsession.send_message(mail)


# returns a list of all content that is stored locally for a specific site
def getStoredHashes(name):
    result = []
    filename = get_site_cache_path(name, ".hash")
    if os.path.exists(filename):
        with open(filename, 'r') as thefile:
            for line in thefile:
                result.append(line.rstrip())

    return result


# updates list of content that is stored locally for a specific site
def storeHashes(name, contentHashes):
    with open(get_site_cache_path(name, ".hash"), 'w') as thefile:
        for h in contentHashes:
            thefile.write(h + "\n")


def runParsers(parsers, contentList=None):
    if contentList is None:
        contentList = []

    for parser in parsers:
        contentList = parser.performAction(contentList)

    return contentList


# Helper to get cache file path for a site
def get_site_cache_path(site_name, extension):
    cache_dir = Path(config.workingDirectory)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{site_name}{extension}"

# Helper to diff and store content
def diff_and_store(site_name, new_content, encoding='utf-8'):
    cache_path = get_site_cache_path(site_name, ".cache")
    if cache_path.exists():
        with cache_path.open('r', encoding=encoding, errors='replace') as f:
            old_content = f.read()
        diff = list(difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile='previous',
            tofile='current',
            lineterm=''
        ))
        with cache_path.open('w', encoding=encoding) as f:
            f.write(new_content)
        return '\n'.join(diff)
    else:
        with cache_path.open('w', encoding=encoding) as f:
            f.write(new_content)
        return None

def pollWebsites():
    global defaultEncoding
    # parse existing feed or create a new one
    rssfile = config.rssfile
    if not os.path.isabs(rssfile):
        rssfile = os.path.join(config.workingDirectory, rssfile)

    if config.enableRSSFeed:
        if os.path.isfile(rssfile):
            feedXML = etree.parse(rssfile)
        else:
            feedXML = etree.parse(io.StringIO(emptyfeed))

    # start polling sites
    mailsSent = 0
    for site in config.sites:
        logger.debug('polling site [' + site['name'] + '] ...')
        receiver = site.get('receiver', config.receiver)
        diff_mode = site.get('diff', False)
        logger.info(f"diff_mode: {diff_mode}")
        try:
            contentList = runParsers(site['parsers'])
        except Exception as e:
            # if something went wrong, notify the user
            subject = '[' + site['name'] + '] WARNING'
            logger.warning('WARNING: ' + str(e))
            if config.enableMailNotifications:
                if config.maxMailsPerSession == -1 or mailsSent < config.maxMailsPerSession:
                    sendmail(receivers=[receiver], subject=subject, content=str(e), sendAsHtml=False, link=None)
                    mailsSent = mailsSent + 1
            if config.enableRSSFeed:
                feedXML.xpath('//channel')[0].append(genFeedItem(subject, str(e), "", 0))
            continue

        sessionHashes = []
        changedContents = []
        fileHashes = getStoredHashes(site['name'])
        for content in contentList:

            contenthash = hashlib.md5(content.content.encode(content.encoding)).hexdigest()
            if contenthash not in fileHashes:
                if (not config.enableMailNotifications) or config.maxMailsPerSession == -1 or mailsSent < config.maxMailsPerSession:
                    sessionHashes.append(contenthash)
                    changedContents.append(content)

                    subject = '[' + site['name'] + '] ' + ("Update available" if content.title is None else content.title)
                    display_content = content.content
                    if diff_mode:
                        logger.debug(f"site['name']: {site['name']}, diff_mode: {diff_mode}")
                        diff = diff_and_store(site['name'], content.content, encoding=content.encoding)
                        if diff:
                            display_content = diff
                        else:
                            display_content = '(no previous version, nothing to diff)'
                    logger.info('    ' + subject)
                    logger.info(display_content)
                    if config.enableMailNotifications and len(fileHashes) > 0:
                        if diff_mode:
                            sendAsHtml = False
                        else:
                            sendAsHtml = (content.contenttype == 'html')
                        contentReceivers = [receiver]
                        if content.receivers is not None:
                            contentReceivers.extend(content.receivers)
                        sendmail(receivers=contentReceivers, subject=subject, content=display_content, sendAsHtml=sendAsHtml, link=content.uri, encoding=content.encoding)
                        mailsSent = mailsSent + 1

                    if config.enableRSSFeed:
                        feedXML.xpath('//channel')[0].append(genFeedItem(subject, display_content, content.uri, len(changedContents)))
            else:
                sessionHashes.append(contenthash)

        if 'postRun' in site:
            runParsers(site['postRun'], changedContents)

        if len(changedContents) > 0:
            if site.get("keepHashes", False):
                sessionHashes.extend(fileHashes)
            storeHashes(site['name'], sessionHashes)
            logger.info('        ' + str(len(changedContents)) + ' updates')

    # store feed
    if config.enableRSSFeed:
        for o in feedXML.xpath('//channel/item[position()<last()-' + str(config.maxFeeds - 1) + ']'):
            o.getparent().remove(o)
        with open(rssfile, 'w') as thefile:
            thefile.write(etree.tostring(feedXML, pretty_print=True, xml_declaration=True, encoding=defaultEncoding).decode(defaultEncoding, errors='ignore'))


if __name__ == "__main__":
    configMod = 'config'
    dryrun = None

    parser = argparse.ArgumentParser(description='Mail Website Changes')
    parser.add_argument('-c', '--config', dest='config',
                      default='config',
                      help='config module to use')
    parser.add_argument('-d', '--dry-run', dest='dry_run',
                      help='name of site to do a dry run for')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true',
                      help='suppress all output')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                      help='verbose output')
    args = parser.parse_args()

    config = importlib.import_module(args.config)

    if args.quiet:
        logger.setLevel(logging.WARNING)
    elif args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    if args.dry_run:
        for thesite in config.sites:
            if thesite['name'] == args.dry_run:
                parseResult = runParsers(thesite['parsers'])
                for p in parseResult:
                    logger.info(f"title: {p.title}")
                    logger.info(f"content: {p.content}")
                logger.info(str(len(parseResult)) + " results")
                break
    else:
        try:
            pollWebsites()
        except Exception:
            msg = str(sys.exc_info()[0]) + '\n\n' + traceback.format_exc()
            logger.error(msg)
            if config.receiver != '':
                sendmail(receivers=[config.receiver], subject='[mwc] Something went wrong ...', content=msg, sendAsHtml=False, link=None)

        if mailsession:
            mailsession.quit()
            mailsession = None
