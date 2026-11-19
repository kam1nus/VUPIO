#!/usr/bin/env python3
"""Issue a one-use Pro tester code through the website administrator API."""
import argparse
import json
from pathlib import Path
import urllib.request
from mimic.account import WEBSITE, NoRedirect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--admin-token-file', type=Path, required=True, help='Private administrator token file, outside the checkout')
parser.add_argument('--days', type=int, default=7, choices=range(1,31))
args = parser.parse_args()
token = args.admin_token_file.read_text().strip()
if len(token) != 64: raise SystemExit('Invalid administrator token file.')
request = urllib.request.Request(WEBSITE + '/api/account/tester-code', data=json.dumps({'days':args.days}).encode(),
    headers={'Authorization':'Bearer ' + token, 'Content-Type':'application/json','User-Agent':'VUPIO-Account/1'})
try:
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as result:
        reply = json.load(result)
    print('Tester code:', reply['code'])
    print('Pro access days:', reply['days'])
    print('Redeem within 7 days in VUPIO Account or on the website. Single use.')
except Exception:
    raise SystemExit('Could not issue a tester code. Check the site and administrator token.') from None
