#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os

from bs4 import BeautifulSoup
from bs4.element import Tag as bs4_Tag

__author__ = "Nate Bohman"
__credits__ = ["Nate Bohman"]
__license__ = "LGPL-3"
__maintainer__ = "Nate Bohman"
__email__ = "natrinicle@natrinicle.com"
__status__ = "Production"

COVERAGE_PATH = os.path.abspath(os.path.dirname(__file__))


for filename in os.listdir(COVERAGE_PATH):
    if filename.endswith("_py.html"):
        # Cut off .html and add .source.html
        source_only_filename = "{}.source.html".format(filename[:-5])
        with open(os.path.join(COVERAGE_PATH, filename), "r") as file:
            soup = BeautifulSoup(file.read(), "html.parser")
        source_div = soup.find(id="source")
        source_text_td = source_div.find_all("td", {"class": "text"})[0]
        with open(
            os.path.join(COVERAGE_PATH, source_only_filename), "w"
        ) as output_file:
            for line in source_text_td.contents:
                if isinstance(line, (bs4_Tag)):
                    try:
                        output_file.write("{}\n".format(line))
                    except UnicodeEncodeError:
                        output_file.write(
                            "{}\n".format(line)
                            .encode("ascii", "ignore")
                            .decode("ascii")
                        )
