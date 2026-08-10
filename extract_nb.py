import json
nb = json.load(open('Business_scraper.ipynb', encoding='utf-8'))
for i, c in enumerate(nb['cells']):
    if c['cell_type'] == 'code':
        print(f'--- Cell {i} ---')
        print(''.join(c['source']))
        print()
