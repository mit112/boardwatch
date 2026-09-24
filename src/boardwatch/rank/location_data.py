"""Versioned location catalog: place tokens to ISO-3 countries, plus per-country POSITIVE packs.

DATA, not logic: adding a state, country, city, or region here changes classification without
touching the resolver (`location_gate.resolve_countries`). Two halves (DESIGN-T183 B2):

- the TOKEN MAP — foreign country names, cities, macro-regions and ISO alpha-3 codes, each
  mapped to the countries it names. Universal: it holds no view on which countries count.
- the POSITIVE PACKS — one `CountryPack` per country whose own signals (subdivision codes and
  names, postal codes, cities) must be read BEFORE or AFTER the token map. Only the `usa` pack
  ships; a pack for any other country is the tenant's data, not ours.

The curation rules below were written from the US point of view, because the `usa` pack was the
first one: they are that pack's namesake rules, and a pack for another country needs its own.

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
— and that is the accepted price: the gate must never silently delete a US role (D-251).
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

from dataclasses import dataclass

# Bump when any set below changes, so a downstream cache or report can detect drift.
# 8: tianjin and chongqing, the two direct-administered municipalities CITIES_BY_ISO3 lacked
# (beijing and shanghai were already in), and the 17 provincial capitals it lacked, all CHN. The
# run-474 audit found "Tianjin, Tianjin" reading `unknown` and passing the location filter; the
# store held 35 such strings (bare "Tianjin", "Shenyang", "Urumqi" ...), none naming a US place.
# A municipality is its own province, so its name as a city token also covers "Tianjin, Tianjin":
# the city step runs before the region step, and a region entry for it could never be reached.
# 7: restructured into a token -> ISO-3 map and the `usa` positive pack (DESIGN-T183 B2). The
# flat sets are derived from the per-country maps and are unchanged token for token; every open
# posting's `us / non_us / unknown` reading was measured byte-identical across the change.
# 6: NON_US_ISO3_SUFFIX added, a curated inclusion list read as a trailing comma component
# ("Dublin, IRL"), and fji / png added to NON_US_ISO3. 777 open postings whose every segment
# ended in a non-US alpha-3 code read `unknown` and failed open (CAN 220, IRL 130, KOR 87,
# JPN 80 ...), three of them in the apply lane. The code
# beats a US city token, so "San Francisco,CRI" (Costa Rica) and "Kirkland, QC, CAN" now read
# non-US. The US territories stay out of the set, and so stay fail-open.
# 5: hengelo added. An audit of the post-run apply lane found 4 genuinely foreign postings in
# 203, and Hengelo was the ONLY one a token can fix: the other three are Paris and Dublin, both
# excluded BY NAME above and deliberately left costing us those postings. Measured the way this
# file prescribes -- every posting in the store mentioning `hengelo` is Thales, 17 of them, sole
# location string "Hengelo", and there is NO US namesake it would cost. Latent pool behind it:
# 492 open Thales postings currently classifying `unknown`.
# 4: kaunas / zhubei / wuxi / saint-etienne added to NON_US_CITIES and jiangsu to
# NON_US_REGIONS, from the 2026-08-30 queue audit: six apply-lane postings named a plainly
# foreign office and classified `unknown`, which FAILS OPEN into the apply lane. Each one
# passes the curation test at the top of this file -- name the US employer the token would
# cost you, and there is none. `Dublin` came up in the same batch and is STILL excluded,
# for the reason already written above.
# 3: US_STATE_NAME_TO_ABBREV added and the two state sets derived from it. The classifier's
# own tokens are unchanged — the map exists so `core.normalize.canonical_location` can fold
# "Austin, Texas" and "Austin, TX" to one identity component.
LOCATION_DATA_VERSION = 8

# The one source of truth for US states: both sets below are DERIVED from it, so adding a
# state is one edit, not three that can disagree. Values are USPS abbreviations, which is
# the form `canonical_location` folds every state name to.
#
# "district of columbia" is carried here as a state because every consumer treats DC as one:
# the classifier reads "Washington, DC" as US, and the canonicalizer has to fold
# "Washington, District of Columbia" onto it.
US_STATE_NAME_TO_ABBREV: dict[str, str] = dict({
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
})

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
US_MARKERS = tuple((
    "united states of america",
    "united states",
    "u.s.a.",
    "u.s.a",
    "u.s.",
    "usa",
))

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

# Every foreign token maps to the ISO-3 countries it names. A token naming more than one country
# (a macro-region) maps to all of them, so a tenant targeting one of them reads it as a possible
# home posting. NO token here maps to "USA": a US reading comes only from the `usa` POSITIVE pack
# below, whose strong signals are tried before this map and whose weak ones after it.
COUNTRY_NAMES_BY_ISO3: dict[str, frozenset[str]] = dict(
    ALB=frozenset({"albania"}),
    ARE=frozenset({"uae", "united arab emirates"}),
    ARG=frozenset({"argentina"}),
    ARM=frozenset({"armenia"}),
    AUS=frozenset({"australia"}),
    AUT=frozenset({"austria"}),
    AZE=frozenset({"azerbaijan"}),
    BEL=frozenset({"belgium"}),
    BGD=frozenset({"bangladesh"}),
    BGR=frozenset({"bulgaria"}),
    BIH=frozenset({"bosnia"}),
    BLR=frozenset({"belarus"}),
    BOL=frozenset({"bolivia"}),
    BRA=frozenset({"brazil"}),
    CAN=frozenset({"canada"}),
    CHE=frozenset({"switzerland"}),
    CHL=frozenset({"chile"}),
    CHN=frozenset({"china"}),
    COL=frozenset({"colombia"}),
    CRI=frozenset({"costa rica"}),
    CYP=frozenset({"cyprus"}),
    CZE=frozenset({"czech", "czechia"}),
    DEU=frozenset({"germany", "deutschland"}),
    DNK=frozenset({"denmark"}),
    DOM=frozenset({"dominican republic"}),
    ECU=frozenset({"ecuador"}),
    EGY=frozenset({"egypt"}),
    ESP=frozenset({"spain"}),
    EST=frozenset({"estonia"}),
    FIN=frozenset({"finland"}),
    FRA=frozenset({"france"}),
    GBR=frozenset({"united kingdom", "england", "scotland", "wales", "u.k.", "u.k"}),
    GHA=frozenset({"ghana"}),
    GRC=frozenset({"greece"}),
    GTM=frozenset({"guatemala"}),
    HKG=frozenset({"hong kong"}),
    HND=frozenset({"honduras"}),
    HRV=frozenset({"croatia"}),
    HUN=frozenset({"hungary"}),
    IDN=frozenset({"indonesia"}),
    IND=frozenset({"india"}),
    IRL=frozenset({"ireland"}),
    ISL=frozenset({"iceland"}),
    ISR=frozenset({"israel"}),
    ITA=frozenset({"italy"}),
    JOR=frozenset({"jordan"}),
    JPN=frozenset({"japan"}),
    KAZ=frozenset({"kazakhstan"}),
    KEN=frozenset({"kenya"}),
    KHM=frozenset({"cambodia"}),
    KOR=frozenset({"south korea", "korea"}),
    LBN=frozenset({"lebanon"}),
    LKA=frozenset({"sri lanka"}),
    LTU=frozenset({"lithuania"}),
    LUX=frozenset({"luxembourg"}),
    LVA=frozenset({"latvia"}),
    MAR=frozenset({"morocco"}),
    MDA=frozenset({"moldova"}),
    MEX=frozenset({"mexico"}),
    MKD=frozenset({"north macedonia"}),
    MLT=frozenset({"malta"}),
    MMR=frozenset({"myanmar"}),
    MNE=frozenset({"montenegro"}),
    MUS=frozenset({"mauritius"}),
    MYS=frozenset({"malaysia"}),
    NGA=frozenset({"nigeria"}),
    NLD=frozenset({"netherlands"}),
    NOR=frozenset({"norway"}),
    NPL=frozenset({"nepal"}),
    NZL=frozenset({"new zealand"}),
    PAK=frozenset({"pakistan"}),
    PAN=frozenset({"panama"}),
    PER=frozenset({"peru"}),
    PHL=frozenset({"philippines"}),
    POL=frozenset({"poland"}),
    PRT=frozenset({"portugal"}),
    PRY=frozenset({"paraguay"}),
    QAT=frozenset({"qatar"}),
    ROU=frozenset({"romania"}),
    RUS=frozenset({"russia", "russian federation"}),
    RWA=frozenset({"rwanda"}),
    SAU=frozenset({"saudi arabia"}),
    SGP=frozenset({"singapore"}),
    SRB=frozenset({"serbia"}),
    SVK=frozenset({"slovakia"}),
    SVN=frozenset({"slovenia"}),
    SWE=frozenset({"sweden"}),
    THA=frozenset({"thailand"}),
    TUN=frozenset({"tunisia"}),
    TUR=frozenset({"turkey"}),
    TWN=frozenset({"taiwan"}),
    UGA=frozenset({"uganda"}),
    UKR=frozenset({"ukraine"}),
    URY=frozenset({"uruguay"}),
    VEN=frozenset({"venezuela"}),
    VNM=frozenset({"vietnam"}),
    ZAF=frozenset({"south africa"}),
)

# UNAMBIGUOUS foreign cities only (see the module docstring's curation rule). Provenance of the
# later additions: kaunas / zhubei / wuxi / saint-etienne came from the 2026-08-30 queue audit,
# each a bare office name with no country suffix to do the work; hengelo is version 5 below; and
# buc / basel / penzberg ... yinchuan were added after run 65, every one having reached a ranked
# shortlist through the `unknown` fail-open, each checked against the corpus for a US namesake
# before being admitted (see the rejected list in the module docstring).
CITIES_BY_ISO3: dict[str, frozenset[str]] = dict(
    ARE=frozenset({"dubai", "abu dhabi"}),
    ARG=frozenset({"buenos aires", "rosario"}),
    AUS=frozenset({"sydney", "melbourne", "perth", "brisbane", "adelaide"}),
    AUT=frozenset({"vienna", "klagenfurt"}),
    BEL=frozenset({"brussels", "diegem"}),
    BGD=frozenset({"dhaka"}),
    BGR=frozenset({"sofia"}),
    BRA=frozenset({
        "curitiba", "recife", "brasilia", "sao paulo", "são paulo", "sao jose dos campos",
        "são josé dos campos", "belo horizonte", "rio de janeiro", "joinville", "barueri",
        "varginha", "florianópolis", "florianopolis",
    }),
    CAN=frozenset({
        "toronto", "vancouver", "montreal", "ottawa", "calgary", "mississauga", "kitchener",
        "edmonton", "winnipeg", "quebec city", "saskatoon",
    }),
    CHE=frozenset({"zurich", "zürich", "geneva", "basel", "kaiseraugst"}),
    CHL=frozenset({"santiago"}),
    CHN=frozenset({
        "wuxi", "shanghai", "beijing", "shenzhen", "guangzhou", "chengdu", "hangzhou", "nanjing",
        "suzhou", "foshan", "zhuzhou", "wuhan", "kunming", "jiaxing", "hefei", "xianyang",
        "nanchang", "xian", "jining", "yinchuan",
        # Version 8: the municipalities and provincial capitals the set lacked.
        "tianjin", "chongqing", "shijiazhuang", "taiyuan", "hohhot", "shenyang", "changchun",
        "harbin", "fuzhou", "jinan", "zhengzhou", "changsha", "nanning", "haikou", "guiyang",
        "lhasa", "lanzhou", "xining", "urumqi",
    }),
    CIV=frozenset({"abidjan"}),
    CMR=frozenset({"douala"}),
    COL=frozenset({"bogota", "bogotá", "medellin", "medellín"}),
    CRI=frozenset({"alajuela"}),
    CYP=frozenset({"nicosia"}),
    CZE=frozenset({"prague", "brno"}),
    DEU=frozenset({
        "berlin", "munich", "frankfurt", "hamburg", "cologne", "stuttgart", "dusseldorf",
        "düsseldorf", "penzberg", "kleinmachnow", "grenzach", "böblingen", "boblingen", "mannheim",
    }),
    DNK=frozenset({"copenhagen", "aarhus"}),
    EGY=frozenset({"cairo"}),
    ESP=frozenset({
        "madrid", "barcelona", "seville", "sant cugat del vallès", "sant cugat del valles",
    }),
    EST=frozenset({"tallinn"}),
    FIN=frozenset({"helsinki", "tampere"}),
    FRA=frozenset({
        "saint-etienne", "st. etienne", "st etienne", "lyon", "bordeaux", "lille", "nantes",
        "toulouse", "marseille", "buc", "suresnes",
    }),
    GBR=frozenset({"london", "manchester", "edinburgh", "leeds", "glasgow", "belfast"}),
    GHA=frozenset({"accra"}),
    GRC=frozenset({"athens"}),
    HRV=frozenset({"zagreb"}),
    HUN=frozenset({"budapest"}),
    IND=frozenset({
        "bengaluru", "bangalore", "gurugram", "gurgaon", "hyderabad", "pune", "chennai", "mumbai",
        "delhi", "new delhi", "noida", "kolkata", "ahmedabad", "kochi", "coimbatore", "jaipur",
        "indore", "nagpur", "surat",
    }),
    IRL=frozenset({"cork", "galway"}),
    ISL=frozenset({"reykjavik", "reykjavík"}),
    ISR=frozenset({"tel aviv", "haifa", "herzliya", "ramat gan", "rehovot"}),
    ITA=frozenset({"milan", "rome", "turin", "bologna", "milano"}),
    JOR=frozenset({"amman"}),
    JPN=frozenset({"tokyo", "osaka", "nagoya", "fukuoka", "yokohama", "kyoto", "hino"}),
    KAZ=frozenset({"astana"}),
    KEN=frozenset({"nairobi"}),
    KOR=frozenset({"seoul", "busan", "incheon", "seongnam"}),
    LBN=frozenset({"beirut"}),
    LTU=frozenset({"kaunas", "vilnius"}),
    LVA=frozenset({"riga"}),
    MAR=frozenset({"casablanca"}),
    MEX=frozenset({
        "guadalajara", "mexico city", "monterrey", "queretaro", "tijuana", "ciudad juarez",
        "ciudad juárez", "huixquilucan de degollado",
    }),
    MYS=frozenset({"petaling jaya"}),
    NGA=frozenset({"lagos"}),
    NLD=frozenset({
        "hengelo", "amsterdam", "rotterdam", "the hague", "utrecht", "eindhoven", "drachten",
    }),
    NOR=frozenset({"oslo", "bergen", "lindesnes"}),
    NZL=frozenset({"auckland", "wellington", "christchurch"}),
    PAK=frozenset({"islamabad", "lahore"}),
    PER=frozenset({"lima"}),
    POL=frozenset({
        "warsaw", "krakow", "kraków", "poznan", "wroclaw", "wrocław", "lodz", "łódź", "warszawa",
    }),
    PRT=frozenset({"lisbon", "porto", "carnaxide"}),
    QAT=frozenset({"doha"}),
    ROU=frozenset({"bucharest", "timisoara"}),
    SAU=frozenset({"riyadh"}),
    SGP=frozenset({"singapore"}),
    SLV=frozenset({"san salvador"}),
    SRB=frozenset({"belgrade"}),
    SVK=frozenset({"bratislava"}),
    SVN=frozenset({"ljubljana"}),
    SWE=frozenset({"stockholm", "gothenburg", "danderyd", "uppsala"}),
    TUN=frozenset({"tunis"}),
    TUR=frozenset({"istanbul", "ankara"}),
    TWN=frozenset({"zhubei", "taipei", "kaohsiung", "hsinchu", "taoyuan", "taichung"}),
    UGA=frozenset({"kampala"}),
    UKR=frozenset({"kyiv", "kiev"}),
    ZAF=frozenset({"cape town", "johannesburg", "durban"}),
)

_EU = frozenset(
    {
        "AUT", "BEL", "BGR", "CYP", "CZE", "DEU", "DNK", "ESP", "EST", "FIN", "FRA", "GRC",
        "HRV", "HUN", "IRL", "ITA", "LTU", "LUX", "LVA", "MLT", "NLD", "POL", "PRT", "ROU",
        "SVK", "SVN", "SWE",
    }
)
_EUROPE = frozenset(
    {
        "ALA", "ALB", "AND", "ARM", "AUT", "AZE", "BEL", "BGR", "BIH", "BLR", "CHE", "CYP",
        "CZE", "DEU", "DNK", "ESP", "EST", "FIN", "FRA", "FRO", "GBR", "GEO", "GGY", "GIB",
        "GRC", "HRV", "HUN", "IMN", "IRL", "ISL", "ITA", "JEY", "LIE", "LTU", "LUX", "LVA",
        "MCO", "MDA", "MKD", "MLT", "MNE", "NLD", "NOR", "POL", "PRT", "ROU", "RUS", "SJM",
        "SMR", "SRB", "SVK", "SVN", "SWE", "TUR", "UKR", "VAT",
    }
)
_MIDDLE_EAST = frozenset(
    {
        "ARE", "BHR", "CYP", "EGY", "IRN", "IRQ", "ISR", "JOR", "KWT", "LBN", "OMN", "PSE",
        "QAT", "SAU", "SYR", "TUR", "YEM",
    }
)
_AFRICA = frozenset(
    {
        "AGO", "BDI", "BEN", "BFA", "BWA", "CAF", "CIV", "CMR", "COD", "COG", "COM", "CPV",
        "DJI", "DZA", "EGY", "ERI", "ESH", "ETH", "GAB", "GHA", "GIN", "GMB", "GNB", "GNQ",
        "KEN", "LBR", "LBY", "LSO", "MAR", "MDG", "MLI", "MOZ", "MRT", "MUS", "MWI", "MYT",
        "NAM", "NER", "NGA", "REU", "RWA", "SDN", "SEN", "SHN", "SLE", "SOM", "SSD", "STP",
        "SWZ", "SYC", "TCD", "TGO", "TUN", "TZA", "UGA", "ZAF", "ZMB", "ZWE",
    }
)
_ASIA = frozenset(
    {
        "AFG", "ARE", "ARM", "AZE", "BGD", "BHR", "BRN", "BTN", "CHN", "CYP", "GEO", "HKG",
        "IDN", "IND", "IRN", "IRQ", "ISR", "JOR", "JPN", "KAZ", "KGZ", "KHM", "KOR", "KWT",
        "LAO", "LBN", "LKA", "MAC", "MDV", "MMR", "MNG", "MYS", "NPL", "OMN", "PAK", "PHL",
        "PRK", "PSE", "QAT", "SAU", "SGP", "SYR", "THA", "TJK", "TKM", "TLS", "TUR", "TWN",
        "UZB", "VNM", "YEM",
    }
)
_OCEANIA = frozenset(
    {
        "AUS", "COK", "FJI", "FSM", "KIR", "MHL", "NCL", "NFK", "NIU", "NRU", "NZL", "PLW",
        "PNG", "PYF", "SLB", "TKL", "TON", "TUV", "VUT", "WLF", "WSM",
    }
)
_LATAM = frozenset(
    {
        "ARG", "BHS", "BLZ", "BOL", "BRA", "BRB", "CHL", "COL", "CRI", "CUB", "DOM", "ECU",
        "GTM", "GUF", "GUY", "HND", "HTI", "JAM", "MEX", "NIC", "PAN", "PER", "PRY", "SLV",
        "SUR", "TTO", "URY", "VEN",
    }
)

# Foreign macro-regions and subnational regions. Transcontinental countries sit in every region
# they touch: a region test only ever widens what a target can KEEP. The subnational names
# ("Saxony", "Thuringia") arrive as a whole location string where a provider names the state
# instead of the city; Chinese provinces arrive as the second segment of a "City, Province"
# location with no country ever named ("Wuxi, Jiangsu"), exactly as the German states do.
REGIONS_TO_ISO3: dict[str, frozenset[str]] = dict({
    "emea": _EUROPE | _MIDDLE_EAST | _AFRICA,
    "apac": _ASIA | _OCEANIA,
    "latam": _LATAM,
    "europe": _EUROPE,
    "uk": frozenset({"GBR"}),
    "eu": _EU,
    "asia": _ASIA,
    "anz": frozenset({"AUS", "NZL"}),
    "middle east": _MIDDLE_EAST,
    "africa": _AFRICA,
    "saxony": frozenset({"DEU"}),
    "thuringia": frozenset({"DEU"}),
    "jiangsu": frozenset({"CHN"}),
})

# The flat token sets, DERIVED so the per-country maps above stay the one source of truth.
NON_US_COUNTRIES = frozenset().union(*COUNTRY_NAMES_BY_ISO3.values())
NON_US_CITIES = frozenset().union(*CITIES_BY_ISO3.values())
NON_US_REGIONS = frozenset(REGIONS_TO_ISO3)

# ISO 3166-1 alpha-3 country codes, for providers that emit a country code where no city token
# exists: a site code ("VNM06-01-Ho Chi Minh"), a dash prefix ("BGR-Varna"), or a parenthesised
# suffix ("Remote (IND)"). Only the ALPHA-3 form is read: a 2-letter code collides with 51 US
# state abbreviations ("IN" is Indiana as often as India, "DE" Delaware as often as Germany)
# and with department and compass prefixes ("IT -", "SE -"). "usa" is deliberately absent.
# So are the US territories "pri", "gum", "vir", "asm", "mnp" and "umi": they stay `unknown`,
# fail-open, because whether a territory counts as the US is a policy question, not this table's.
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
        # Fiji and Papua New Guinea: seen as a trailing ", FJI" / ", PNG" in the open pool.
        "fji", "png",
    }
)

# ISO 3166-1 alpha-3, every officially assigned code (249), UPPERCASE as the standard writes it.
# The closed vocabulary of a profile's `target_countries`: a code outside it is a typed failure at
# the write boundary, never a new bucket. Alpha-3 only, for the reason `NON_US_ISO3` gives.
ISO3166_ALPHA3 = frozenset(
    {
        "ABW", "AFG", "AGO", "AIA", "ALA", "ALB", "AND", "ARE", "ARG", "ARM", "ASM", "ATA",
        "ATF", "ATG", "AUS", "AUT", "AZE", "BDI", "BEL", "BEN", "BES", "BFA", "BGD", "BGR",
        "BHR", "BHS", "BIH", "BLM", "BLR", "BLZ", "BMU", "BOL", "BRA", "BRB", "BRN", "BTN",
        "BVT", "BWA", "CAF", "CAN", "CCK", "CHE", "CHL", "CHN", "CIV", "CMR", "COD", "COG",
        "COK", "COL", "COM", "CPV", "CRI", "CUB", "CUW", "CXR", "CYM", "CYP", "CZE", "DEU",
        "DJI", "DMA", "DNK", "DOM", "DZA", "ECU", "EGY", "ERI", "ESH", "ESP", "EST", "ETH",
        "FIN", "FJI", "FLK", "FRA", "FRO", "FSM", "GAB", "GBR", "GEO", "GGY", "GHA", "GIB",
        "GIN", "GLP", "GMB", "GNB", "GNQ", "GRC", "GRD", "GRL", "GTM", "GUF", "GUM", "GUY",
        "HKG", "HMD", "HND", "HRV", "HTI", "HUN", "IDN", "IMN", "IND", "IOT", "IRL", "IRN",
        "IRQ", "ISL", "ISR", "ITA", "JAM", "JEY", "JOR", "JPN", "KAZ", "KEN", "KGZ", "KHM",
        "KIR", "KNA", "KOR", "KWT", "LAO", "LBN", "LBR", "LBY", "LCA", "LIE", "LKA", "LSO",
        "LTU", "LUX", "LVA", "MAC", "MAF", "MAR", "MCO", "MDA", "MDG", "MDV", "MEX", "MHL",
        "MKD", "MLI", "MLT", "MMR", "MNE", "MNG", "MNP", "MOZ", "MRT", "MSR", "MTQ", "MUS",
        "MWI", "MYS", "MYT", "NAM", "NCL", "NER", "NFK", "NGA", "NIC", "NIU", "NLD", "NOR",
        "NPL", "NRU", "NZL", "OMN", "PAK", "PAN", "PCN", "PER", "PHL", "PLW", "PNG", "POL",
        "PRI", "PRK", "PRT", "PRY", "PSE", "PYF", "QAT", "REU", "ROU", "RUS", "RWA", "SAU",
        "SDN", "SEN", "SGP", "SGS", "SHN", "SJM", "SLB", "SLE", "SLV", "SMR", "SOM", "SPM",
        "SRB", "SSD", "STP", "SUR", "SVK", "SVN", "SWE", "SWZ", "SXM", "SYC", "SYR", "TCA",
        "TCD", "TGO", "THA", "TJK", "TKL", "TKM", "TLS", "TON", "TTO", "TUN", "TUR", "TUV",
        "TWN", "TZA", "UGA", "UKR", "UMI", "URY", "USA", "UZB", "VAT", "VCT", "VEN", "VGB",
        "VIR", "VNM", "VUT", "WLF", "WSM", "YEM", "ZAF", "ZMB", "ZWE",
    }
)

# The codes read as a trailing comma component ("Dublin, IRL"), matched UPPERCASE as written so
# "Remote, Can" never reads as Canada. It is a WEAKER shape than a site-code prefix or a
# parenthesised suffix, because a US location can end in an uppercase three-letter token that is
# not a country: an airport or site code, or a time zone ("Austin, AUS", "Remote, EST"). And an
# exclusion list cannot close, since some FAA location identifier exists for almost every
# three-letter string. So this is an INCLUSION list, the D-294 pattern: only codes OBSERVED as the
# trailing suffix of a foreign location in the open pool (2026-09-22: CAN 220, IRL 130, KOR 87,
# JPN 80, DEU 43, TWN 38, ITA 27, CHN 23, MYS 20, FRA 18, GBR 10, ROU 9, ... and CRI, KWT), each
# passing the curation test at the top of this file. PHL, IND and AUS were observed too and are
# left out BY NAME: they are the airport codes of Philadelphia, Indianapolis and Austin, which
# employers use as site codes, so 10 open postings ending in them stay `unknown`, as they were.
# Audited the same day over ALL 3,713 stored segments, open and closed, that end in one of these
# codes: every place before the code is foreign (Shanghai, Hiroshima, London, Toronto, ...). A town
# that merely HAS an FAA identifier among them (Challis CHL, Tullahoma THA) is the gazetteer
# namesake the curation rule excludes: no posting writes a US place as "Town, <airport id>".
# Every member must also be in `NON_US_ISO3`.
NON_US_ISO3_SUFFIX = frozenset(
    {
        "aut", "bel", "bra", "can", "chl", "chn", "cri", "deu", "esp", "fin", "fji", "fra",
        "gbr", "idn", "irl", "isr", "ita", "jpn", "kor", "kwt", "mex", "mys", "nld", "per",
        "png", "pol", "rou", "tha", "twn", "vnm",
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


@dataclass(frozen=True)
class CountryPack:
    """One country's POSITIVE signals, so the resolver can confirm that country, not guess it.

    ``strong`` signals are read BEFORE the foreign token map: an explicit country marker, a
    bare country token, a subdivision name, or a TWO-letter subdivision code as a "City, XX"
    suffix, uppercase as written. That order is what keeps "Vienna, VA" and "London, ON" in
    their pack's country. ``weak`` signals (a postal code, a city) are read AFTER it, so a
    foreign city sharing a pack city's name ("Manchester, UK") still reads as foreign.
    """

    iso3: str
    markers: frozenset[str]
    bare_tokens: frozenset[str]
    subdivision_names: frozenset[str]
    subdivision_codes: frozenset[str]
    postal_pattern: str | None
    cities: frozenset[str]


USA_PACK = CountryPack(
    iso3="USA",
    markers=frozenset(US_MARKERS),
    # A bare "US"/"U.S." is an explicit US signal and must win within a segment that also names
    # a foreign place ("US, Canada"). Word-bounded, so it never fires inside "Houston".
    bare_tokens=frozenset({"us", "u.s.", "u.s"}),
    subdivision_names=US_STATE_NAMES,
    subdivision_codes=US_STATE_ABBREVS,
    # Read after the token map, so a foreign postal code beside its country
    # ("Berlin, Germany 10115") stays foreign.
    postal_pattern=r"(?<!\d)\d{5}(?:-\d{4})?(?!\d)",
    cities=US_CITIES,
)

# The packs that ship. Any other country's pack comes from the tenant's config (DESIGN-T183 Q6).
BUNDLED_PACKS = tuple((USA_PACK,))
