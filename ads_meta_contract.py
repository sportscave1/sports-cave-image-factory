"""Shared, non-secret Meta ad defaults used by Sports Cave Ads workflows."""

META_AD_URL_PARAMETERS = (
    "utm_source=facebook&utm_medium=paid_social&utm_campaign={{campaign.name}}"
    "&utm_content={{ad.name}}&utm_term={{adset.name}}&placement={{placement}}"
    "&utm_id={{campaign.id}}&adset_id={{adset.id}}&ad_id={{ad.id}}"
    "&site_source={{site_source_name}}"
)

META_DEFAULT_CTA = "SHOP_NOW"
