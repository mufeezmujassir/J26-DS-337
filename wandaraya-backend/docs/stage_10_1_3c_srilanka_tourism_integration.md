# Stage 10.1.3C — Sri Lanka Tourism Offline Integration

**Status:** COMPLETE_WITH_LIMITATIONS. This is an offline, fixture-driven
implementation. No request was made to `srilanka.travel`.

The integration supports typed fixture extraction for attraction, activity,
destination, event, public-holiday, travel-information, and operating-info
pages. Extracted facts remain null where absent. It preserves source URL,
publication date, descriptions, categories, events/holidays, ticket links,
restrictions, fee text, and explicit schedule material; it never invents
coordinates, prices, dates, activities, or opening hours.

Entity matching classifies a fixture as `existing_match`, `ambiguous_match`, or
`proposed_new_entity` using name/location evidence supplied to the pure function.
It never creates, merges, or overwrites attractions. Explicit fixture schedules
reuse the Stage 10.1.2 parser; beaches and natural sites with no explicit hours
remain unknown. Events, public holidays, Poya/observance data, and tourism
events remain distinct typed facts, and no closure or suitability conclusion is
drawn from a date alone.

The permission record is intentionally conservative: reported verbal permission
is undocumented, and automated fetch, storage, embeddings, redistribution and
commercial reuse remain false pending written scope confirmation. The inventory
contains all supplied sections but leaves unverified URLs null rather than
guessing or crawling.

Before a controlled live pilot, obtain written scope, attribution, retention,
embedding and redistribution terms; exact permitted URLs/domains; robots/access
approval; request rate and timeout policy; named contact; and manual review
process. Gate 2 remains blocked until those approvals exist.

Offline validation: **65 focused tests** and **87 broader regression tests**
passed, with no failures or skipped tests. One third-party deprecation warning
was emitted in the broader suite.
