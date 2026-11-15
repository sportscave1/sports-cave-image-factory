# Product Page Lifestyle Mockups

Only these three cards remain active. The Social Lifestyle Mockups heading and cards 04–17 are removed from the page labels, active prompt registry and render groups. No layout, CSS, upload or clipboard implementation was changed. Historical uploaded assets and ZIP mappings remain compatible. Ads retains its existing close-up prompt foundation independently.

## Room choices

### 01 - Man Cave (Product Page)

1. Modern man cave with pool table
2. Sports collector room with tasteful display shelving
3. Luxury media room / entertainment den
4. Premium garage lounge / workshop retreat
5. Whiskey lounge / gentleman’s retreat

### 02 - Office (Product Page)

1. Modern home office
2. Executive office
3. Creative studio workspace
4. Reading study / library nook
5. Minimal work-from-home nook

### 03 - Living Room (Product Page)

1. Minimal living room
2. Luxury apartment lounge
3. Minimal bedroom
4. Hotel-style bedroom suite
5. Family lounge / relaxed sitting room

## Camera choices

1. Straight on
2. Slightly angled from the left
3. Slightly angled from the right

## Final template structure

Each card uses the same complete template below, with its own category-specific room list. Product name, sport category and the existing artwork reference precede this body. Existing room-style guidance and shared product/photorealism locks follow it. Saved administrator edits remain supported; the resolved scene block takes precedence over older room/angle instructions.

```text
Product name: {product_name}
Sport category: {sport_category}
Reference image: {existing_reference_instruction}

Create a 1024 x 1024 photorealistic ecommerce lifestyle mockup using the supplied framed Sports Cave artwork as the exact reference.
Preserve the supplied artwork and frame exactly: colours, text, badge, layout, complete outer frame and landscape proportions. Do not redesign, crop, blur, stretch, warp or distort the artwork.
Place the frame realistically on a wall at eye level with believable scale, physical mounting, natural contact shadows and restrained glass reflections that do not obscure the artwork.
Keep the framed artwork the clear focal hero. Use a premium, clean, minimal, polished and uncluttered room that supports rather than competes with the product.
Use believable natural light, controlled highlights and realistic material texture. Avoid excessive darkness, noisy props, neon signs, distracting memorabilia, extra wall art, people, text overlays and watermarks.
Use the single selected room and camera direction below. Allow subtle variation in furniture layout, lighting direction, wall material, decor, room proportions and composition within that room style.
Keep perspective natural and architectural lines straight. No extreme side angles, awkward perspective, fisheye or independently distorted frame/artwork. The design must remain clearly readable.
The final scene must look like real professional interior photography, not an AI-generated or over-styled room.

SPORTS CAVE PRODUCT PAGE SCENE V1
Selected room: {one_random_room_from_this_card_list}
Selected camera angle: {one_random_angle}
{matching_angle_guidance}
Use only this selected room and angle; they replace any earlier room or camera direction. Keep the artwork unchanged and the room premium, minimal and product-page friendly.
END PRODUCT PAGE SCENE

{existing_sport_room_guidance}
{existing_shared_product_and_photorealism_locks}
```

Angle guidance:

- **Straight on:** View the framed artwork directly front-facing, balanced and clean.
- **Slightly angled from the left:** Position the camera a little to the left for a subtle perspective view of the room and artwork.
- **Slightly angled from the right:** Position the camera a little to the right for a subtle perspective view of the room and artwork.

## Selection and persistence

Room and angle use separate random.choice calls for each newly generated card: 15 possible combinations per card. Choices are stored in the existing generated prompt text/files and reused on copy, upload and rerun. Random draws may legitimately repeat; there is no forced rotation. Restored legacy prompt packs regenerate into the current three-card collection. Stored prompt edits cannot erase or duplicate the selected scene block.

## Code

- `mockup_product_prompts.py`: editable room/angle lists, shared template, selection and preservation helpers.
- `image_factory.py`: three active prompt specifications and generation integration; preserved Ads foundation.
- `app.py`: three card labels, single rendering group, legacy-pack refresh and selection preservation when reading prompt edits.
- Regression tests: `tests/test_mockup_product_variations.py`, `tests/test_mockup_prompt_preview.py`, `tests/test_mockup_reels.py`, `tests/test_mockup_eight_image_manifest.py`, and the close-up foundation test in `tests/test_ads_page.py`.

## Verification

Streamlit AppTest covers initial render, restored packs, routing, upload processing, retained upload slots, and ZIP inclusion. Unit tests cover every one of the 45 category/room/angle combinations, independent fresh draws, saved-pack stability, prompt edits, asset exports and the Ads close-up dependency. Tests using bare app imports run separately from AppTest to avoid Streamlit global layout state contamination.

The broader carousel suite has four pre-existing Instant Experience hash snapshot mismatches (also reproduced using HEAD:image_factory.py); those unrelated snapshots were not changed. No production images were generated, no external uploads were made, and nothing was deployed.
