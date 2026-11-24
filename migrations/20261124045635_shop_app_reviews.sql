-- Native Shop app provenance. Private Flow inbox is read using existing scopes.
ALTER TABLE sc_reviews DROP CONSTRAINT IF EXISTS sc_reviews_source_check;
ALTER TABLE sc_reviews ADD CONSTRAINT sc_reviews_source_check
 CHECK(source IN ('csv','judgeme','sports_cave','shop_app')) NOT VALID;
ALTER TABLE sc_reviews VALIDATE CONSTRAINT sc_reviews_source_check;
