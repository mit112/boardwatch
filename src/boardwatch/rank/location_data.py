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
"""

from __future__ import annotations

# Bump when any set below changes, so a downstream cache or report can detect drift.
LOCATION_DATA_VERSION = 1

US_STATE_ABBREVS = frozenset(
    {
        "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in",
        "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv",
        "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn",
        "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
    }
)

US_STATE_NAMES = frozenset(
    {
        "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
        "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
        "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
        "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada",
        "new hampshire", "new jersey", "new mexico", "new york", "north carolina",
        "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island",
        "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
        "washington", "west virginia", "wisconsin", "wyoming", "district of columbia",
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
    }
)

# Non-US macro-regions: no US component, so a hard US gate drops them.
NON_US_REGIONS = frozenset(
    {"emea", "apac", "latam", "europe", "uk", "eu", "asia", "anz", "middle east", "africa"}
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
