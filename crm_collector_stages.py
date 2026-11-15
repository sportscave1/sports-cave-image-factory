"""Reviewed lifecycle body proposals, never automatic draft migrations."""
from copy import deepcopy
from crm_collector_templates import source as template_source, document as template_document
from crm_lifecycle_definition import COPY

PREFIX = 'builtin-collector-stage-v2-'
STAGES = {
 'welcome-1': ('welcome', 1, 'collector-welcome', 'Welcome to Sports Cave', 'Discover artwork that brings the sporting stories you love into your space. Explore the collection and find a moment that means something to you.'),
 'welcome-2': ('welcome', 2, 'build-collection', 'Find your sporting story', 'Explore artwork from the sports and moments that matter to you. Browse the collection for the details of each piece.'),
 'welcome-3': ('welcome', 3, 'build-collection', 'Begin a collection with meaning', 'A collection begins with a sporting moment you want to remember. Discover available artwork and explore its individual edition details.'),
 'post_purchase-1': ('post_purchase', 1, 'collected-artwork', 'Thank you for choosing Sports Cave', 'Your artwork is part of your sporting story. Explore your collection while you look forward to enjoying your piece. Follow your order updates for its progress.'),
 'post_purchase-2': ('post_purchase', 2, 'collected-artwork', 'Explore My Collection', 'Visit your Sports Cave account to explore your artwork and numbered edition details. Once your certificate is available, you can access it securely in My Collection.'),
 'post_purchase-3': ('post_purchase', 3, 'build-collection', 'Build on your sporting story', 'Discover artwork that belongs alongside the sporting moments you have collected. Explore each piece for current availability and edition details.'),
 'win_back-1': ('win_back', 1, 'collector-reengagement', 'Revisit your sporting story', 'Return to the moments that inspired your collection and discover related artwork to explore.'),
 'win_back-2': ('win_back', 2, 'build-collection', 'More sporting stories to explore', 'Explore available artwork from the sports that inspired your collection. Find another moment worth keeping.'),
 'win_back-3': ('win_back', 3, 'build-collection', 'Your collection can grow', 'A collection grows one meaningful piece at a time. Explore artwork that connects with your sporting story.'),
 'win_back-4': ('win_back', 4, 'collector-reengagement', 'One more moment to explore', 'Whenever you choose to revisit your collection, explore the sporting moments that mean something to you.'),
}


def mapping():
    return [dict(key=key, trigger=t, email=n, template=design, days=COPY[t][n-1][2],
                 anchor=COPY[t][n-1][3], enabled=key!='win_back-4')
            for key,(t,n,design,_,_) in STAGES.items()]


def source(identity):
    _,_,design,title,copy=STAGES[identity.removeprefix(PREFIX)]
    return template_source(design,wording=(title,copy))


def document(identity):
    key=identity.removeprefix(PREFIX)
    _,_,design,title,copy=STAGES[key]
    doc=template_document(design)
    doc['content'].update(subject=title,preheader=copy)
    from crm_middle_sections import commit_middle
    commit_middle(doc,[dict(id='collector-body',type='html',visible=True,html_number=1,html=source(key))])
    return doc


def library_rows(trigger):
    return [dict(id=PREFIX+key,name=f'{trigger.replace("_"," ").title()} {n} · {title} · replace body',
                 version=2,builtin=True) for key,(t,n,_,title,_) in STAGES.items() if t==trigger and key!='win_back-4']


def apply(doc,identity):
    """Explicit library Use only. Existing save_flow archives the old revision.

    Replace middle content, including legacy recommendation blocks, as one
    reviewed operation. Preserve global branding, audience and incentive settings.
    """
    key=identity.removeprefix(PREFIX)
    if key=='win_back-4':raise ValueError('Win Back Email 4 remains disabled; no application is offered.')
    proposed=deepcopy(doc);prepared=document(key)
    from crm_middle_sections import commit_middle
    from crm_campaign_content import validate_document
    commit_middle(proposed,prepared['middle_sections'])
    proposed['content_mode']='HTML'
    proposed['content'].update({k:prepared['content'][k] for k in ('subject','preheader')})
    proposed['copy_reviewed']=False
    proposed['template_ref']={'id':PREFIX+key,'version':2,'name':STAGES[key][3]}
    validate_document(proposed)
    doc.update(proposed)
