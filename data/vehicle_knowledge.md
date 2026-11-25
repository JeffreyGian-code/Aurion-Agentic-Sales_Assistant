# Vehicle recommendation evidence

Each row applies to one catalogue variant. The ID, brand, model, variant and body type must match the inventory row. A blank variant cell represents a database null. The app reads listed prices from inventory.

Topics are lowercase identifiers such as `commuting`, `parking` and `automatic`. Use `confirmed` when the cited source verifies the criterion for the exact variant. Use `indicative` when the source gives a reason to consider the variant and suitability still needs checking. Add one row per ID and topic. Keep reasons and sources as plain text without pipe characters.

The initial entries use the hatchback body type recorded for these variants. The catalogue has no variant-level transmission or parking measurements.

| ID | Brand | Model | Variant | Body type | Topic | Strength | Reason | Source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 41 | Hyundai | i20 | Base | Hatchback | commuting | indicative | Its catalogue-listed hatchback body style makes it a candidate for city commuting. | Aurion seed catalogue (database/seed.sql), ID 41 |
| 41 | Hyundai | i20 | Base | Hatchback | parking | indicative | Its catalogue-listed hatchback body style makes it worth comparing for tight parking. Check dimensions and parking aids. | Aurion seed catalogue (database/seed.sql), ID 41 |
| 111 | Maruti Suzuki | Baleno | Base | Hatchback | commuting | indicative | Its catalogue-listed hatchback body style makes it a candidate for city commuting. | Aurion seed catalogue (database/seed.sql), ID 111 |
| 111 | Maruti Suzuki | Baleno | Base | Hatchback | parking | indicative | Its catalogue-listed hatchback body style makes it worth comparing for tight parking. Check dimensions and parking aids. | Aurion seed catalogue (database/seed.sql), ID 111 |
| 131 | Maruti Suzuki | Swift | Base | Hatchback | commuting | indicative | Its catalogue-listed hatchback body style makes it a candidate for city commuting. | Aurion seed catalogue (database/seed.sql), ID 131 |
| 131 | Maruti Suzuki | Swift | Base | Hatchback | parking | indicative | Its catalogue-listed hatchback body style makes it worth comparing for tight parking. Check dimensions and parking aids. | Aurion seed catalogue (database/seed.sql), ID 131 |
| 161 | Tata | Tiago | Base | Hatchback | commuting | indicative | Its catalogue-listed hatchback body style makes it a candidate for city commuting. | Aurion seed catalogue (database/seed.sql), ID 161 |
| 161 | Tata | Tiago | Base | Hatchback | parking | indicative | Its catalogue-listed hatchback body style makes it worth comparing for tight parking. Check dimensions and parking aids. | Aurion seed catalogue (database/seed.sql), ID 161 |
| 181 | Toyota | Glanza | Base | Hatchback | commuting | indicative | Its catalogue-listed hatchback body style makes it a candidate for city commuting. | Aurion seed catalogue (database/seed.sql), ID 181 |
| 181 | Toyota | Glanza | Base | Hatchback | parking | indicative | Its catalogue-listed hatchback body style makes it worth comparing for tight parking. Check dimensions and parking aids. | Aurion seed catalogue (database/seed.sql), ID 181 |
