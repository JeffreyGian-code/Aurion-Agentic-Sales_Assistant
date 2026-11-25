# Vehicle recommendation evidence

Each row applies to one catalogue variant. The ID, brand, model, variant and body type must match the inventory row. A blank variant cell represents a database null. The app reads listed prices from inventory.

Topics are lowercase identifiers such as `commuting`, `parking` and `automatic`. Use `confirmed` when the cited source verifies the criterion for the exact variant. Use `indicative` when the source gives a reason to consider the variant and suitability still needs checking. Add one row per ID and topic. Keep reasons and sources as plain text without pipe characters.

The pilot uses the body types recorded for these variants. The reasons describe how a buyer might compare those body styles. The catalogue has no variant-level transmission, boot measurements or parking measurements.

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
| 1 | Honda | Amaze | Base | Sedan | luggage | indicative | This sedan is a candidate if you want a separate boot for shopping, suitcases or family luggage. Check boot dimensions with your bags. | Aurion seed catalogue (database/seed.sql), ID 1 |
| 11 | Honda | City | Base | Sedan | luggage | indicative | Consider this sedan when a separate boot for suitcases on longer family trips matters. Check usable boot space for this variant. | Aurion seed catalogue (database/seed.sql), ID 11 |
| 51 | Hyundai | Verna | Base | Sedan | luggage | indicative | This sedan is worth comparing for buyers who want to keep bags in a separate boot away from the passenger cabin. Check usable space with the luggage you carry. | Aurion seed catalogue (database/seed.sql), ID 51 |
| 21 | Honda | Elevate | Base | SUV | suv_layout | indicative | Consider this SUV body style if you prefer the layout of an SUV for family outings. Check seat access and driving position in person. | Aurion seed catalogue (database/seed.sql), ID 21 |
| 151 | Tata | Nexon | Base | SUV | suv_layout | indicative | This SUV is worth comparing if an SUV cabin layout matters for family outings. Try getting in and out and check how the seats work for your passengers. | Aurion seed catalogue (database/seed.sql), ID 151 |
| 134 | Maruti Suzuki | Swift | V | Hatchback | loading | indicative | A hatchback layout is worth comparing if you regularly load groceries or bags through the rear hatch. Check the opening and floor height for the things you carry. | Aurion seed catalogue (database/seed.sql), ID 134 |
