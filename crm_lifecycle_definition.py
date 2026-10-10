"""Draft-only lifecycle starter content, using the existing document contract."""
from copy import deepcopy
from crm_automation_definition import new_flow, email_step
from crm_campaign_content import new_document
from crm_html_workspace import html_document

TRIGGERS = frozenset(('welcome', 'post_purchase', 'win_back'))
VERSION = 1
# Offsets are absolute from the named verified event, never from send time.
COPY = {
 'welcome': [
  ('Welcome to the Collector Vault', 'Welcome to Sports Cave — Where Legends Live On', 0, 'subscription', 'Explore The Collection', 'Welcome to Sports Cave', 'Discover premium limited-edition sports wall art celebrating the athletes, teams and moments you love. Welcome to the Collector Vault: a place to begin your collection and find the sporting stories that belong on your wall.', 'Browse by sport and find a moment that means something to you.'),
  ('Find Your Sporting Legend', 'Every Legend Has a Moment Worth Remembering', 3, 'subscription', 'Find Your Legend', 'Find your sporting legend', 'A defining play. A favourite team. A moment you still remember. Explore Sports Cave collections and find artwork that brings your sporting story home.', 'Choose your favourite sport to explore the available editions.'),
  ('Own a Piece of Sporting History', 'Some Sporting Moments Deserve More Than a Memory', 7, 'subscription', 'Claim Your Edition', 'A collection with meaning', 'Explore our limited-to-100 editions and discover the story behind each artwork. Check the individual product page for its edition details and whether a certificate of authenticity is included.', 'Find an edition you will enjoy displaying for years to come.')],
 'post_purchase': [
  ('Welcome to the Collection', 'Your Sporting Legend Is Now Part of Your Collection', 1, 'payment', 'Explore Sports Cave', 'Welcome to the collection', 'Thank you for choosing Sports Cave. Your artwork celebrates a sporting story worth keeping, with thoughtful craftsmanship and the character of a limited-edition collection.', 'Keep your order updates handy for the latest information about your purchase. In the meantime, discover the stories behind the collection.'),
  ('Display Your Sporting Legacy', 'Give Your Sporting Legend the Spotlight It Deserves', 7, 'delivery', 'Share Your Setup', 'Give your legend its spotlight', 'Choose a place where you can enjoy your artwork every day. Keep it away from direct sunlight and moisture, and follow the care and mounting instructions supplied with your item.', 'We would love to see your setup. Visit our contact page to share a photo of your collection.'),
  ('Build Your Collection', 'One Legend Deserves Another', 45, 'payment', 'Explore More Legends', 'Build your collection', 'Your next piece can tell another part of your sporting story. Explore available artwork from your favourite sports and discover complementary pieces for your collection.', 'Choose a legend that belongs alongside the one you already love.')],
 'win_back': [
  ("See What's New", 'Your Next Sporting Legend Might Be Waiting', 90, 'last_purchase', 'Discover New Editions', 'Your next sporting story', 'There is always another sporting story to discover. Take a look through the current Sports Cave collection and see what speaks to you today.', 'Browse the latest available editions and check each product for its details.'),
  ("More Legends You'll Love", 'We Found More Legends Worth Collecting', 105, 'last_purchase', 'Explore Your Collection', 'More legends to explore', 'Return to the sports, athletes and moments that inspired your collection. Explore complementary artwork and find another story worth displaying.', 'Start with your favourite sport and see the available collection.'),
  ("The Collector's Reminder", "Greatness Doesn't Fade. Your Collection Can Grow.", 120, 'last_purchase', 'Explore Available Editions', 'Greatness stays with you', 'A collection grows one meaningful piece at a time. Discover limited-edition sports artwork and check the product page for current availability and edition details.', 'Find a piece you connect with, at your own pace.'),
  ('One Last Look', 'One More Sporting Moment Worth Remembering', 150, 'last_purchase', 'Return to Sports Cave', 'One more moment worth remembering', 'A gentle final invitation to revisit Sports Cave. Whenever you are ready, explore the available artwork and find a sporting moment you would love to bring home.', 'Thank you for being part of the Sports Cave collector community.')]
}

def expanded_flow(trigger, sections=None):
    if trigger not in TRIGGERS: raise ValueError('Unsupported lifecycle flow')
    flow = new_flow(trigger)
    flow.update(lifecycle_version=VERSION, exit_on_purchase=trigger != 'post_purchase',
                inactive_days=90, reentry_days=90 if trigger == 'win_back' else 0,
                fulfilment_fallback_days=14)
    flow['emails'] = []
    for i, (name, subject, days, anchor, cta, headline, intro, body) in enumerate(COPY[trigger]):
        doc = new_document()
        doc['content'].update(subject=subject, preheader=body, eyebrow='THE COLLECTOR VAULT',
            headline=headline, intro=intro, body=body, cta_label=cta,
            cta_url='https://www.sportscaveshop.com/pages/contact' if anchor == 'delivery' else 'https://www.sportscaveshop.com/collections/all')
        doc['notes'] = 'Draft only. Verify catalogue links, product recommendations and any product-specific claims before activation. No incentive is configured.'
        doc = html_document(doc)
        if trigger=='win_back' and i==0:doc['tags']=['lifecycle-new-editions']
        if sections: doc['html_sections'] = deepcopy(sections)
        if trigger=='win_back' or trigger=='welcome' and i>0 or trigger=='post_purchase' and i==2:
            from crm_middle_sections import middle_sections,commit_middle,DISPLAY
            from crm_lifecycle_products import SECTION_ID
            commit_middle(doc,middle_sections(doc)+[dict(id=SECTION_ID,type='catalogue',name='Product recommendations',visible=True,products=[],
                settings={'headline':'Explore the collection','subtext':'','columns':2,'display':{field:field in ('image','title','cta') for field in DISPLAY},'cta':cta})])
        doc['smart_hours']=24
        step = email_step(doc, days * 86400)
        step.update(name=name, enabled=not (trigger == 'win_back' and i == 3), anchor=anchor)
        if trigger=='post_purchase':step['requires_fulfilment']=i>0
        flow['emails'].append(step)
    return flow

def locked(row):
    return bool((row.get('config') or {}).get('draft', {}).get('lifecycle_version'))

def timing_label(step):
    labels = {'subscription':'confirmed subscription', 'payment':'verified payment',
              'delivery':'confirmed delivery (or configured fulfilment fallback)', 'last_purchase':'latest qualifying purchase'}
    return ' after ' + labels[step['anchor']]
