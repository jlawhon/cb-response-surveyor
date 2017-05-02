#!/usr/bin/env python

"""Given Cb Enterprise Response process search criteria, return a unique set
of matches based on:

- hostname
- username
- process path
- process command-line

Results are written to a CSV file. 

Requires a valid cbapi-ng credential file containing a Cb Enterprise Response
server URL and corresponding API token.

Requires one or more JSON-formatted definition files (examples provided) or a
Cb Response query as input.
"""

import argparse
import csv
import json
import os
import sys

from cbapi.response import CbEnterpriseResponseAPI
from cbapi.response.models import Process


def err(msg):
    """Format msg as an ERROR and print to stderr.
    """
    msg = 'ERROR: %s\n' % msg
    sys.stderr.write(msg)
    return
    

def process_search(cb_conn, query, query_base=None):
    """Perform a single Cb Response query and return a unique set of
    results.
    """
    results = set()

    query += query_base

    try:
        for proc in cb_conn.select(Process).where(query):
            results.add((proc.hostname.lower(),
                        proc.username.lower(), 
                        proc.path,
                        proc.cmdline))
    except KeyboardInterrupt:
        print "Caught CTRL-C. Returning what we have . . ."

    return results

def nested_process_search(cb_conn, criteria, query_base=None):
    """Perform Cb Response queries for one or more programs and return a 
    unique set of results per program.
    """
    results = set()

    try:
        for search_field,terms in criteria.iteritems():
            query = '(' + ' OR '.join('%s:%s' % (search_field, term) for term in terms) + ')'
            query += query_base

            for proc in cb_conn.select(Process).where(query):
                results.add((proc.hostname.lower(),
                            proc.username.lower(), 
                            proc.path,
                            proc.cmdline))
    except KeyboardInterrupt:
        print "Caught CTRL-C. Returning what we have . . ."

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", type=str, action="store", 
                        help="Output filename prefix.")
    parser.add_argument("--profile", type=str, action="store",
                        help="The credentials.response profile to use.")

    # Time boundaries for the survey
    parser.add_argument("--days", type=int, action="store",
                        help="Number of days to search.")
    parser.add_argument("--minutes", type=int, action="store",
                        help="Number of days to search.")

    # Survey criteria
    i = parser.add_mutually_exclusive_group(required=True)
    i.add_argument('--deffile', type=str, action="store", 
                        help="Definition file to process (must end in .json).")
    i.add_argument('--defdir', type=str, action="store", 
                        help="Directory containing multiple definition files.")
    i.add_argument('--query', type=str, action="store", 
                        help="A single Cb query to execute.")
    i.add_argument('--iocfile', type=str, action="store", 
                        help="IOC file to process. One IOC per line. REQUIRES --ioctype")

    # IOC survey criteria
    parser.add_argument('--ioctype', type=str, action="store", 
                        help="One of: ipaddr, domain, md5")

    args = parser.parse_args()

    if (args.iocfile is not None and args.ioctype is None):
        parser.error('--iocfile requires --ioctype')

    if args.prefix:
        output_filename = '%s-survey.csv' % args.prefix
    else:
        output_filename = 'survey.csv' 

    query_base = ''
    if args.days:
        query_base += ' start:-%dm' % (args.days*1440)
    elif args.minutes:
        query_base += ' start:-%dm' % args.minutes

    definition_files = []
    if args.deffile:
        if not os.path.exists(args.deffile):
            err('deffile does not exist')
            sys.exit(1)
        definition_files.append(args.deffile)
    elif args.defdir:
        if not os.path.exists(args.defdir):
            err('defdir does not exist')
            sys.exit(1)
        for root, dirs, files in os.walk(args.defdir):
            for filename in files:
                if filename.endswith('.json'):
                    definition_files.append(os.path.join(root, filename))
        
    output_file = file(output_filename, 'wb')
    writer = csv.writer(output_file)
    writer.writerow(["endpoint","username","process_path","cmdline","program","source"])
    
    if args.profile:
        cb = CbEnterpriseResponseAPI(profile=args.profile)
    else:
        cb = CbEnterpriseResponseAPI()

    if args.query:
        result_set = process_search(cb, args.query, query_base)

        for r in result_set:
            row = [r[0], r[1], r[2], r[3], args.query, 'query']
            row = [col.encode('utf8') if isinstance(col, unicode) else col for col in row]
            writer.writerow(row)
    elif args.iocfile:
        with open(args.iocfile) as iocfile:
            data = iocfile.readlines()
            for ioc in data:
                ioc = ioc.strip()
                query = '%s:%s' % (args.ioctype, ioc)
                result_set = process_search(cb, query, query_base)

                for r in result_set:
                    row = [r[0], r[1], r[2], r[3], ioc, 'ioc']
                    row = [col.encode('utf8') if isinstance(col, unicode) else col for col in row]
                    writer.writerow(row)
    else:
        for definition_file in definition_files:
            print "Processing definition file: %s" % definition_file
            basename = os.path.basename(definition_file)
            source = os.path.splitext(basename)[0]

            fh = file(definition_file, 'rb')
            programs = json.load(fh)
            fh.close()

            for program,criteria in programs.iteritems():
                print "--> %s" % program

                result_set = nested_process_search(cb, criteria, query_base)

                for r in result_set:
                    row = [r[0], r[1], r[2], r[3], program, source]
                    row = [col.encode('utf8') if isinstance(col, unicode) else col for col in row]
                    writer.writerow(row)

    output_file.close()


if __name__ == '__main__':

    sys.exit(main())
