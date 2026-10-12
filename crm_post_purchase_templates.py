"""Editable repeat HTML over the existing recipient-scoped artwork resolver."""
from crm_collector_images import settings,marker

PREFIX='builtin-post-purchase-gallery-v1-'
DESIGNS={'purchased':'Products Purchased','collections':'Collections of Products Purchased'}


def library_rows():
    return [dict(id=PREFIX+key,name=name,version=1,builtin=True,library_group='Post Purchase') for key,name in DESIGNS.items()]


def source(identity):
    key=identity.removeprefix(PREFIX)
    name=DESIGNS[key]
    config=settings(name,250 if key=='purchased' else 6)
    opening=marker(config).replace('SC_COLLECTOR_IMAGE_V1','SC_COLLECTOR_REPEAT_V1')
    heading='Your artwork, chosen by you' if key=='purchased' else 'Continue your sporting collection'
    quantity='<p style="margin:8px 0;color:#d3b779;font-size:14px;font-family:Arial;line-height:21px">Quantity: [[product.quantity]]</p>' if key=='purchased' else ''
    # All card HTML is authored source, including the editable binding tokens.
    # No frozen layout, automatic draft migration or additional marketing blocks.
    return ('<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#111111"><tr><td style="padding:24px;color:#f4efe5">'
            '<h2 style="font-size:28px;font-family:Georgia;line-height:34px;margin:0 0 20px;color:#f4efe5">'+heading+'</h2>'
            +opening+'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:20px 12px;border-bottom:1px solid #39342b">'
            '<a href="[[product.url]]"><img src="[[product.image]]" alt="[[product.title]]" width="520" style="display:block;width:100%;max-width:520px;height:auto;border:0"></a>'
            '<h3 style="margin:16px 0 8px;color:#f4efe5;font-size:22px;font-family:Georgia;line-height:28px">[[product.title]]</h3>'+quantity
            +'<a href="[[product.url]]" style="color:#d3b779;font-size:14px;font-family:Arial;line-height:21px">Explore artwork</a>'
            '</td></tr></table><!--SC_COLLECTOR_REPEAT_END--></td></tr></table>')
