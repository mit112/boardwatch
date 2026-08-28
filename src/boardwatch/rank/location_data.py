"""Versioned token catalog for the US location classifier (`location_gate.classify_location`).

DATA, not logic: adding a state, country, city, or region here changes classification without
touching the classifier. Kept as module frozensets rather than YAML because the classifier is
pure-Python string work with no per-user override surface yet; if a non-US target country is
ever needed, this is where its tokens go (the classifier stays US-centric until then — a
deliberate v1 limitation, since boardwatch's only user requires US-only).

Curation rule for the city sets: **only unambiguous names.** A city name shared between the US
and abroad (Paris TX / France, Cambridge MA / UK, Dublin OH / Ireland, San Jose CA / Costa
Rica, Naples FL / Italy) is left OUT of both sets, so a state/country suffix disambiguates it
rather than a bare token guessing wrong. That is why the classifier can read "Paris, TX" as US
and "Paris, France" as non-US.

The rule bites hardest on names a review is tempted to "complete". These were each considered
for `NON_US_CITIES` and DELIBERATELY REJECTED, because every one has a real US town a posting
could plausibly name: **Dublin** (OH, CA), **Limerick** (PA, ME), **Birmingham** (AL, MI),
**Uxbridge** (MA), **Abingdon** (VA, MD), **Cambridge** (MA), **Warren** (MI, OH, NJ),
**Ontario** (CA), **Valencia** (CA), **Moscow** (ID), **Zwolle** (LA), **Best** (an English
word). Leaving them out costs real foreign postings — 23 Irish `Dublin` roles stay in the pool
— and that is the accepted price: the gate must never silently delete a US role (Mit's ruling).
Do not add them without a country suffix doing the work instead.

"Plausibly" is the operative word, and it means a US namesake that could realistically appear
as a job location, not merely one that exists in a gazetteer. `Warren` is out because Warren MI
is GM's headquarters; `Dublin` because Dublin OH is Cardinal Health's. `Milano` is IN despite
Milano TX existing, because that is a Milam County hamlet of a few hundred people with no
employer, while Milano is how Italian-sourced ATS feeds spell Milan. Apply the same test to
anything added later: name the US employer the token would cost you. If you cannot, it is safe;
if you can, leave it out. (`Zwolle` is out on caution rather than this test — Zwolle LA is also
a hamlet, so it could be admitted, but nothing in the corpus needs it.)
"""

from __future__ import annotations

# Bump when any set below changes, so a downstream cache or report can detect drift.
# 3: US_STATE_NAME_TO_ABBREV added and the two state sets derived from it. The classifier's
# own tokens are unchanged — the map exists so `core.normalize.canonical_location` can fold
# "Austin, Texas" and "Austin, TX" to one identity component.
LOCATION_DATA_VERSION = 3

# The one source of truth for US states: both sets below are DERIVED from it, so adding a
# state is one edit, not three that can disagree. Values are USPS abbreviations, which is
# the form `canonical_location` folds every state name to.
#
# "district of columbia" is carried here as a state because every consumer treats DC as one:
# the classifier reads "Washington, DC" as US, and the canonicalizer has to fold
# "Washington, District of Columbia" onto it.
US_STATE_NAME_TO_ABBREV: dict[str, str] = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar", "california": "ca",
    "colorado": "co", "connecticut": "ct", "delaware": "de", "florida": "fl", "georgia": "ga",
    "hawaii": "hi", "idaho": "id", "illinois": "il", "indiana": "in", "iowa": "ia",
    "kansas": "ks", "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms",
    "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv",
    "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm", "new york": "ny",
    "north carolina": "nc", "north dakota": "nd", "ohio": "oh", "oklahoma": "ok",
    "oregon": "or", "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut", "vermont": "vt",
    "virginia": "va", "washington": "wa", "west virginia": "wv", "wisconsin": "wi",
    "wyoming": "wy", "district of columbia": "dc",
}

US_STATE_ABBREVS = frozenset(US_STATE_NAME_TO_ABBREV.values())

US_STATE_NAMES = frozenset(US_STATE_NAME_TO_ABBREV)

# WHOLE comma-separated segments that name the United States, for `canonical_location`.
# Deliberately NOT merged into US_MARKERS below: that tuple is matched as a SUBSTRING by the
# classifier, where a two-letter "us" would fire inside "Prussia" or "Houston". Segment
# equality makes the short forms safe, so they live here instead.
US_COUNTRY_SEGMENTS = frozenset(
    {
        "united states of america", "united states", "usa", "u.s.a.", "u.s.a", "u.s.", "us",
    }
)

# Multi-word first so the longest match is tried before "u.s." / "usa".
US_MARKERS = (
    "united states of america",
    "united states",
    "u.s.a.",
    "u.s.a",
    "u.s.",
    "usa",
)

US_CITIES = frozenset(
    {
        "san francisco", "south san francisco", "new york", "new york city", "nyc", "seattle",
        "san jose", "chicago", "austin", "boston", "palo alto", "los angeles", "denver",
        "pittsburgh", "tarrytown", "waltham", "mountain view", "sunnyvale", "cupertino",
        "menlo park", "bellevue", "redmond", "atlanta", "dallas", "houston", "san diego",
        "san mateo", "santa clara", "irvine", "plano", "raleigh", "durham", "philadelphia",
        "phoenix", "portland", "san antonio", "nashville", "charlotte", "detroit", "miami",
        "minneapolis", "salt lake city", "kansas city", "san bruno", "foster city",
        "brooklyn", "bethesda", "reston", "mclean", "fremont", "oakland", "berkeley",
        "culver city", "santa monica", "kirkland", "boulder", "ann arbor", "provo",
        "chandler", "tempe", "scottsdale", "cincinnati", "cleveland", "indianapolis", "tampa",
        "orlando", "jacksonville", "sacramento", "el segundo", "pasadena", "alpharetta",
        "addison", "westlake", "chapel hill", "santa barbara", "san ramon", "sandy springs",
    }
)

NON_US_COUNTRIES = frozenset(
    {
        "united kingdom", "england", "scotland", "wales", "u.k.", "u.k", "canada", "india",
        "germany", "france", "ireland", "netherlands", "spain", "italy", "poland", "romania",
        "israel", "japan", "china", "singapore", "south korea", "korea", "taiwan", "australia",
        "new zealand", "brazil", "mexico", "argentina", "chile", "colombia", "portugal",
        "sweden", "norway", "denmark", "finland", "switzerland", "austria", "belgium",
        "czech", "czechia", "hungary", "greece", "turkey", "ukraine", "russia", "egypt",
        "south africa", "nigeria", "kenya", "uae", "united arab emirates", "saudi arabia",
        # Spelled-out forms that the ungrouped alternation used to catch only by accident.
        "deutschland", "russian federation",
        "qatar", "pakistan", "bangladesh", "vietnam", "thailand", "malaysia", "indonesia",
        "philippines", "hong kong", "luxembourg", "estonia", "lithuania", "latvia",
        "bulgaria", "croatia", "serbia", "slovakia", "slovenia", "iceland", "costa rica",
        "peru", "uruguay", "rwanda", "morocco", "tunisia", "ghana", "uganda", "armenia",
        "azerbaijan", "kazakhstan", "sri lanka", "nepal", "cambodia", "myanmar", "jordan",
        "lebanon", "cyprus", "malta", "north macedonia", "bosnia", "montenegro", "albania",
        "moldova", "belarus", "mauritius", "panama", "ecuador", "venezuela", "bolivia",
        "paraguay", "guatemala", "dominican republic", "honduras",
    }
)

# UNAMBIGUOUS non-US cities only (see the module docstring's curation rule).
NON_US_CITIES = frozenset(
    {
        "london", "toronto", "bengaluru", "bangalore", "vancouver", "amsterdam", "tokyo",
        "taipei", "shanghai", "madrid", "sydney", "tel aviv", "berlin", "montreal",
        "gurugram", "gurgaon", "hyderabad", "seoul", "singapore", "beijing", "shenzhen",
        "melbourne", "munich", "barcelona", "milan", "zurich", "zürich", "geneva",
        "stockholm", "oslo", "copenhagen", "helsinki", "warsaw", "krakow", "kraków", "prague",
        "budapest", "bucharest", "lisbon", "vienna", "brussels", "manchester", "edinburgh",
        "pune", "chennai", "mumbai", "delhi", "new delhi", "noida", "kolkata", "ahmedabad",
        "istanbul", "ankara", "cairo", "lagos", "nairobi", "dubai", "abu dhabi", "riyadh",
        "doha", "cork", "galway", "ottawa", "calgary", "mississauga", "kitchener",
        "guadalajara", "mexico city", "bogota", "bogotá", "buenos aires", "santiago", "lima",
        "haifa", "herzliya", "ramat gan", "reykjavik", "reykjavík", "rome", "frankfurt",
        "osaka", "belgrade", "kyiv", "kiev", "athens", "bratislava", "ljubljana", "zagreb",
        "sofia", "tallinn", "riga", "vilnius", "rotterdam", "the hague", "utrecht",
        "eindhoven", "hamburg", "cologne", "stuttgart", "dusseldorf", "düsseldorf", "leeds",
        "glasgow", "belfast", "lyon", "bordeaux", "lille", "nantes", "toulouse", "marseille",
        "seville", "turin", "bologna", "porto", "gothenburg", "aarhus", "bergen", "tampere",
        "poznan", "wroclaw", "wrocław", "brno", "timisoara", "medellin", "medellín", "rosario",
        "curitiba", "recife", "brasilia", "monterrey", "queretaro", "tijuana", "cape town",
        "johannesburg", "durban", "accra", "kampala", "casablanca", "tunis", "amman",
        "beirut", "nicosia", "kochi", "coimbatore", "jaipur", "indore", "nagpur", "surat",
        "nagoya", "fukuoka", "yokohama", "kyoto", "busan", "incheon", "kaohsiung", "hsinchu",
        "guangzhou", "chengdu", "hangzhou", "nanjing", "suzhou", "perth", "brisbane",
        "adelaide", "auckland", "wellington", "christchurch", "edmonton", "winnipeg",
        "quebec city", "taoyuan", "sao paulo", "são paulo", "milano",
        # Added after run 65: every one of these reached a ranked shortlist through the
        # `unknown` fail-open, and each was checked against the corpus for a US namesake
        # before being admitted (see the rejected list in the module docstring).
        "buc", "basel", "penzberg", "kleinmachnow", "suresnes", "kaiseraugst", "grenzach",
        "böblingen", "boblingen", "mannheim", "lodz", "łódź", "klagenfurt", "danderyd",
        "uppsala", "petaling jaya", "seongnam", "hino", "taichung", "warszawa", "carnaxide",
        "sant cugat del vallès", "sant cugat del valles", "sao jose dos campos",
        "são josé dos campos", "belo horizonte", "rio de janeiro", "joinville", "barueri",
        "varginha", "florianópolis", "florianopolis", "ciudad juarez", "ciudad juárez",
        "huixquilucan de degollado", "alajuela", "san salvador", "drachten", "diegem",
        "lindesnes", "islamabad", "lahore", "dhaka", "rehovot", "astana", "saskatoon",
        "abidjan", "douala", "foshan", "zhuzhou", "wuhan", "kunming", "jiaxing", "hefei",
        "xianyang", "nanchang", "xian", "jining", "yinchuan",
    }
)

# Non-US macro-regions and subnational regions: no US component, so a hard US gate drops them.
# The subnational names ("Saxony", "Thuringia") arrive as a whole location string where a
# provider names the state instead of the city.
NON_US_REGIONS = frozenset(
    {
        "emea", "apac", "latam", "europe", "uk", "eu", "asia", "anz", "middle east", "africa",
        "saxony", "thuringia",
    }
)

# ISO 3166-1 alpha-3 country codes, for providers that emit a country code where no city token
# exists: a site code ("VNM06-01-Ho Chi Minh"), a dash prefix ("BGR-Varna"), or a parenthesised
# suffix ("Remote (IND)"). Only the ALPHA-3 form is read: a 2-letter code collides with 51 US
# state abbreviations ("IN" is Indiana as often as India, "DE" Delaware as often as Germany)
# and with department and compass prefixes ("IT -", "SE -"). "usa" is deliberately absent.
NON_US_ISO3 = frozenset(
    {
        "afg", "alb", "and", "are", "arg", "arm", "aus", "aut", "aze", "bel", "bgd", "bgr",
        "bih", "blr", "bra", "can", "che", "chl", "chn", "civ", "cmr", "cod", "col", "cri",
        "cyp", "cze", "deu", "dnk", "dom", "ecu", "egy", "esp", "est", "eth", "fin", "fra",
        "gbr", "geo", "gha", "grc", "gtm", "hkg", "hnd", "hrv", "hun", "idn", "ind", "irl",
        "isl", "isr", "ita", "jor", "jpn", "kaz", "ken", "khm", "kor", "kwt", "lbn", "lka",
        "ltu", "lux", "lva", "mar", "mda", "mex", "mkd", "mlt", "mmr", "mus", "mys", "nga",
        "nld", "nor", "npl", "nzl", "pak", "pan", "per", "phl", "pol", "prt", "pry", "qat",
        "rou", "rus", "rwa", "sau", "sgp", "slv", "srb", "svk", "svn", "swe", "tha", "tun",
        "tur", "twn", "tza", "uga", "ukr", "ury", "uzb", "ven", "vnm", "zaf",
    }
)

# Multi-region tokens that INCLUDE the US: genuinely undecidable for a strict gate, so unknown.
AMBIGUOUS_REGIONS = frozenset(
    {"americas", "north america", "worldwide", "anywhere", "global", "asia pacific", "remote"}
)

# Geography-free segments — a work arrangement, a placeholder, or an office nickname stub. They
# never decide us/non_us; they are skipped so a real geographic segment beside them still counts.
POLICY_ONLY = frozenset(
    {
        "remote", "hybrid", "on-site", "onsite", "on site", "in-office", "in office",
        "n/a", "na", "flexible", "distributed", "headquarters", "hq", "multiple locations",
        "various", "other", "unspecified", "tbd", "",
    }
)
