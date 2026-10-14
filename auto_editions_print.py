"""SKU-specific evidence; never maps an unframed variant to a framed SKU."""
import json
import re
from pathlib import Path


def describe(variant,manifest,sku=None):
    evidence=json.loads((Path(__file__).parent/'data/auto_editions_supplier_evidence.json').read_text())
    spec=evidence.get(sku)
    if spec and str(variant).lower().startswith('unframed') and spec['product_kind']=='framed':
        raise ValueError('Framed supplier geometry cannot be applied to an unframed variant.')
    pixels=manifest['dimensions'];physical=spec.get('printable_mm') if spec else None
    advertised=re.search(r'(\d+(?:\.\d+)?)\s*[x\u00d7]\s*(\d+(?:\.\d+)?)\s*cm',str(variant))
    advertised_mm=sorted([float(n)*10 for n in advertised.groups()],reverse=pixels[0]>=pixels[1]) if advertised else None
    return dict(advertised_mm=advertised_mm,advertised_geometry_verified=False,
        advertised_effective_ppi=[round(p*25.4/mm,2) for p,mm in zip(pixels,advertised_mm)] if advertised_mm else None,
        source_dimensions=manifest['source_dimensions'],prepared_dimensions=pixels,
        output_dimensions=pixels,sku=sku,effective_ppi=[round(p*25.4/mm,2) for p,mm in zip(pixels,physical)] if physical else None,
        source_effective_ppi=[round(p*25.4/mm,2) for p,mm in zip(manifest['source_dimensions'],physical)] if physical else None,
        print_status='TEST / NOT PRINT READY',supplier=spec,
        remaining=['Exact variant/SKU mapping','Bleed','Safe margins','Colour profile','Artwork quality approval'])


def exact_export_geometry(source_dimensions,sku):
    spec=json.loads((Path(__file__).parent/'data/auto_editions_supplier_evidence.json').read_text()).get(sku)
    if not spec:raise ValueError('No exact supplier dimensions for this SKU.')
    target=spec['pixel_dimensions']
    if source_dimensions[0]*target[1]!=source_dimensions[1]*target[0]:
        raise ValueError('Supplier ratio differs. Cropping, stretching and unapproved padding are forbidden.')
    return target
