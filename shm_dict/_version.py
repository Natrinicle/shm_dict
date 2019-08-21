#!/usr/bin/env python
# -*- coding: utf-8 -*-

__version__ = "2019.08.21.23.49"
__version_info__ = tuple([int(num) for num in __version__.split(".")])


if __name__ == "__main__":
    from datetime import datetime

    # Open this file in read plus write mode
    with open(__file__, "r+") as file:
        contents = ""

        # Calculate the version strings
        old_version = __version__
        new_version = datetime.utcnow().strftime("%Y.%m.%d.%H.%M")

        # Read through current file and replace
        # the old datetime stamp with the new
        # UTC datetime stamp
        for line in file.read().split("\n"):
            if line.startswith("__version__ = "):
                line = '__version__ = "{}"'.format(new_version)
            contents = "{}{}\n".format(contents, line)

        # Remove extraneous newline from end of contents
        contents = contents[:-1]

        # Seek back to the beginning of the file
        file.seek(0)
        # Erase the contents
        file.truncate()
        # Write the new contents
        file.write(contents)
        print("Changing version from {} to {}".format(old_version, new_version))
