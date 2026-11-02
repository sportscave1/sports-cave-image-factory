"""Visible, controlled premium glazing for new USA/Australia IE prompts only."""
MARKER = 'VISIBLE PREMIUM GLASS'
REQUIREMENT = (
    'For every framed edition: VISIBLE PREMIUM GLASS — the edition must visibly read as premium glass, never an unglazed or matte-looking print. '
    'Require natural, scene-consistent reflections across a controlled portion of the glass, with believable reflected shapes, '
    'restrained surface highlights and natural falloff matching the actual light source and assigned camera angle. '
    'Keep faces, action, subjects and defining edition text clear. Product recognition takes priority over excessive glare, '
    'but never over visible glazing: reduce or reposition obstructive reflections rather than remove them. '
    'At a 256 × 256 preview, both the subject and the glass surface must remain recognisable; frame-edge highlights alone do not count. '
    'No invisible glazing, opaque streaks, bright window grids over important details, artificial shine, acrylic appearance or flat pasted-on artwork. '
    'Preserve realistic frame-edge highlights and mounting shadows, owner-confirmed premium glass and the verified physical product. '
    'No size or glazing confirmation is required. Preserve unframed products without adding a frame or pane.'
)
CHECK = 'GLAZING CHECK: Confirm visibly recognisable premium glass with controlled scene-consistent surface reflections; keep subjects and defining text clear. Reduce or reposition excessive glare, never remove glazing visibility.'


def active(visual):
    return MARKER in str((visual or {}).get('glazing_treatment') or '')


def apply(prompt):
    # Replace conflicting clauses at their source positions, not an appended override.
    from ads_ie_visual_systems import GLAZING_REQUIREMENT
    from ads_ie_usa import GLAZING
    prompt = prompt.replace(GLAZING_REQUIREMENT, REQUIREMENT).replace(GLAZING, REQUIREMENT)
    for old in (
        'GLAZING CHECK: Every framed edition must show believable surface reflections clearly visible at thumbnail size.',
        'GLAZING CHECK: Product recognition takes priority over reflection visibility at thumbnail size.',
    ):
        prompt = prompt.replace(old, CHECK)
    prompt = prompt.replace(
        'flag missing or imperceptible surface reflections on every framed edition at 256 × 256; frame-edge highlights alone do not count',
        'confirm recognisable glass at 256 × 256 through controlled scene-consistent surface reflections while keeping subjects and defining text clear; frame-edge highlights alone do not count')
    prompt = prompt.replace(
        'check premium glazing without obscuring faces, action or defining edition text; thumbnail recognition takes priority',
        'confirm visibly recognisable premium glass and clear faces, action and defining text; product recognition takes priority over excessive glare, never over visible glazing')
    return prompt
