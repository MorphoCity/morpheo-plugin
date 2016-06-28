""" Return key from plugin  metadata
"""
from __future__ import print_function
import sys

def read_metadata( filename, key=None ):
    from ConfigParser import SafeConfigParser
    parser = SafeConfigParser()
    parser.optionxform = str
    parser.read(filename)
    if key is not None:
        return parser.get("general",key)
    else:
        return parser.items()

if len(sys.argv) < 3:
    print("Usage: python metadata.py <file> <key>")
    sys.exit(1)

print(read_metadata(sys.argv[1],sys.argv[2]))    


