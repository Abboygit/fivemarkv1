import re

src = open('src/dashboard/server.py', encoding='utf-8').read()
page = src.split('PAGE = ', 1)[1]
m = re.search(r'"""(.*)"""', page, re.S)
html = m.group(1)
scripts = re.findall(r'<script>(.*?)</script>', html, re.S)
open('page_check.js', 'w', encoding='utf-8').write('\n'.join(scripts))
open('check_ok.txt', 'w').write('blocks=%d' % len(scripts))
