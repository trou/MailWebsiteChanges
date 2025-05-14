#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright: (2013-2017) Michael Till Beck <Debianguru@gmx.de>
# License: GPL-2.0+


# We collect xpath snippets at this place:
# <a href="https://github.com/Debianguru/MailWebsiteChanges/wiki/snippets">Snippet collection</a>
# Feel free to contribute!


from mwctools import URLReceiver as uri
from mwctools import CommandReceiver as command
from mwctools import XPathParser as xpath
from mwctools import CSSParser as css
from mwctools import RegExParser as regex
from mwctools import Content
from mwctools import Parser


# Each site dictionary can have an optional 'diff' boolean option:
#   'diff': True  # If set, only show the diff (unified diff format) when the website changes, and store the latest version in config.workingDirectory.
sites = [

         {'name': 'example-css',
          'parsers': [uri(uri='https://github.com/mtill', contenttype='html'),
                      css(contentcss='div')
                     ]
         },

         {'name': 'example-xpath',
          'parsers': [uri(uri='https://example-webpage.com/test', contenttype='html'),
                      xpath(contentxpath='//div[contains(concat(\' \', normalize-space(@class), \' \'), \' package-version-header \')]')
                     ],
          'diff': True
         },

         {'name': 'my-script',
          'parsers': [command(command='/home/user/script.sh', contenttype='text'),
                      regex(contentregex='^.*$')
                     ]
         }

]

workingDirectory = '/path-to-data-dir/MailWebsiteChanges-data'

enableMailNotifications = False
maxMailsPerSession = -1
sender = 'me@mymail.com'
smtphost = 'mysmtpprovider.com'
useTLS = True
smtpport = 587
smtpusername = sender
smtppwd = 'mypassword'
receiver = 'me2@mymail.com'

enableRSSFeed = False
rssfile = 'feed.xml'
maxFeeds = 100


