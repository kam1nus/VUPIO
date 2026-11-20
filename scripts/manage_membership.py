#!/usr/bin/env python3
"""Manage complimentary Pro access and promo campaigns. Keep the admin token outside Git."""
import argparse
import json
from pathlib import Path
import urllib.request
from mimic.account import WEBSITE, NoRedirect

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--admin-token-file',type=Path,required=True)
parser.add_argument('--action',choices=['tester-code','overview','grant','revoke','create-code','deactivate-code'],default='tester-code')
parser.add_argument('--days',type=int,default=7)
parser.add_argument('--permanent',action='store_true')
parser.add_argument('--email')
parser.add_argument('--source',choices=['tester','developer','gift'],default='tester')
parser.add_argument('--note',default='')
parser.add_argument('--id')
parser.add_argument('--code',help='Optional custom promo code (8–40 letters/digits)')
parser.add_argument('--label',default='Pro invitation')
parser.add_argument('--max-uses',type=int,default=1)
parser.add_argument('--redeem-days',type=int,default=7)
args=parser.parse_args()
token=args.admin_token_file.read_text().strip()
if len(token)!=64:raise SystemExit('Invalid administrator token file.')
if args.action=='grant' and not args.email:parser.error('--email is required for grant')
if args.action in {'revoke','deactivate-code'} and not args.id:parser.error('--id is required')
body={'days':None if args.permanent else args.days,'email':args.email,'source':args.source,'note':args.note,'id':args.id,'code':args.code,'label':args.label,'max_uses':args.max_uses,'redeem_days':args.redeem_days}
if args.action=='create-code' and args.code is None:body.pop('code')
url='/api/account/tester-code' if args.action=='tester-code' else '/api/admin/'+args.action
request=urllib.request.Request(WEBSITE+url,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','User-Agent':'VUPIO-Account/1'})
try:
    with urllib.request.build_opener(NoRedirect()).open(request,timeout=20) as response:reply=json.load(response)
    print(json.dumps(reply,indent=2))
    if 'code' in reply:print('Save this code now. Only its hash is stored on the server.')
except Exception:raise SystemExit('Membership operation failed. Check the site, access and requested values.') from None
