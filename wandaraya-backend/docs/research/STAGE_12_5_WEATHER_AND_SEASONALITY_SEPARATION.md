# Weather and Seasonality Separation

Weather represents a supported date-specific live forecast or an approved monthly model result. The weather adapter reports historical climatology as unavailable weather evidence and states that it was not used as a date-specific forecast.

Seasonality separately represents persisted historical monthly climate favorability. It reuses `stage12_4f_conservative_v1`, including the district multivariable fallback for weak mappings. It is not a forecast or safety certification.

R3 reduces double counting by combining available weather and seasonality into one climate contribution before combining it with time and holiday/event evidence.
