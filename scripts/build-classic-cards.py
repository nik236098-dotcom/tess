#!/usr/bin/env python3
"""Build independent card SVGs from the bundled LGPL SVG-cards deck.
No external SVG use or live fetching is required when rendering a card.
"""
from pathlib import Path
import copy
import re
import xml.etree.ElementTree as ET
root = Path(__file__).resolve().parents[1]
source = ET.parse(root / 'public/img/classic/deck.svg').getroot()
ns = 'http://www.w3.org/2000/svg'
ET.register_namespace('', ns)
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
ids = {el.attrib['id']: el for el in source.iter() if 'id' in el.attrib}
out = root / 'public/img/classic/cards'
out.mkdir(exist_ok=True)
for suit, label in [('s','spade'), ('h','heart'), ('d','diamond'), ('c','club')]:
    for rank in 'A23456789TJQK':
        name = label + '_' + {'A':'1','T':'10','J':'jack','Q':'queen','K':'king'}.get(rank,rank)
        needed = set()
        def references(el):
            for node in el.iter():
                for key,value in node.attrib.items():
                    refs = ([value[1:]] if key.endswith('href') and value.startswith('#') else []) + re.findall(r'url\(#([^)]*)\)',value)
                    for ref in refs:
                        if ref not in needed:
                            needed.add(ref)
                            references(ids[ref])
        references(ids[name])
        svg = ET.Element('{'+ns+'}svg', {'viewBox':'0 0 169.075 244.64','width':'169.075','height':'244.64'})
        defs = ET.SubElement(svg, '{'+ns+'}defs')
        for ref in sorted(needed): defs.append(copy.deepcopy(ids[ref]))
        svg.append(copy.deepcopy(ids[name]))
        ET.ElementTree(svg).write(out / (rank+suit+'.svg'), encoding='unicode', xml_declaration=False)
print('52 independent classic card faces built')
