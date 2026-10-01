"""Local static production-renderer fixture. No external assets or I/O."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.parse import urlsplit,parse_qs
from tests.test_crm_premium_catalogue import PremiumCatalogueTests
from tests.test_crm_modular_catalogue import catalogue_doc
from crm_campaign_content import render_campaign
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  query=parse_qs(urlsplit(self.path).query);count=int(query.get('n',['4'])[0])
  doc=catalogue_doc();section=PremiumCatalogueTests().section(count)
  section['settings'].update(headline='Collector Favourites' if count>1 else 'Own The Moment',subtext='Iconic moments. Limited editions. Built for the wall.')
  for p in section['products']:p['image']='https://cdn.shopify.com/fixture.png';p['image_alt']=p['title']
  doc['middle_sections']=[section];doc['custom_html']=''
  if self.path.startswith('/art.png'):
   data=Path('C:/Users/hello/AppData/Local/Temp/codex-clipboard-359c45e7-ebe8-49a4-acea-6ba610ccdd92.png').read_bytes();kind='image/png'
  else:
   html=render_campaign(doc)['html'].replace('https://cdn.shopify.com/fixture.png','/art.png')
   if query.get('fallback'):html=html.replace('@media only screen and (min-width:540px){.sc-cat-3{width:33.333%!important}.sc-cat-4{width:25%!important}}','')
   data=html.encode();kind='text/html; charset=utf-8'
  self.send_response(200);self.send_header('Content-Type',kind);self.end_headers();self.wfile.write(data)
HTTPServer(('127.0.0.1',8767),Handler).serve_forever()
