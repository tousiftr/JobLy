import os

# ── Roles ─────────────────────────────────────────────────────────────────────
JOB_ROLES = [
    "analytics engineer", "data analyst", "product analyst",
    "business intelligence", "bi analyst", "bi developer",
    "data analytics", "analytics manager", "analytics lead",
    "data engineer", "analytics", "reporting analyst",
]

# ── Country groups used for UI filtering ─────────────────────────────────────
# Each entry: (display_label, group_key, list_of_match_terms)
COUNTRY_GROUPS = [
    # ── EU Core ──
    ("🇩🇪 Germany",      "germany",     ["germany","deutschland","berlin","munich","münchen","hamburg","frankfurt","cologne","köln","düsseldorf","stuttgart","bremen","hannover","dortmund","essen","leipzig","dresden","nuremberg","nürnberg"]),
    ("🇳🇱 Netherlands",  "netherlands", ["netherlands","holland","amsterdam","rotterdam","eindhoven","utrecht","the hague","den haag","delft","groningen"]),
    ("🇫🇷 France",       "france",      ["france","paris","lyon","marseille","bordeaux","toulouse","nantes","strasbourg","lille","nice","rennes"]),
    ("🇸🇪 Sweden",       "sweden",      ["sweden","sverige","stockholm","gothenburg","göteborg","malmo","malmö","uppsala","linköping"]),
    ("🇩🇰 Denmark",      "denmark",     ["denmark","danmark","copenhagen","københavn","aarhus","odense"]),
    ("🇫🇮 Finland",      "finland",     ["finland","suomi","helsinki","espoo","tampere","oulu","turku"]),
    ("🇳🇴 Norway",       "norway",      ["norway","norge","oslo","bergen","trondheim","stavanger"]),
    ("🇮🇪 Ireland",      "ireland",     ["ireland","éire","dublin","cork","galway","limerick","waterford"]),
    ("🇪🇸 Spain",        "spain",       ["spain","españa","madrid","barcelona","valencia","seville","sevilla","bilbao","malaga","zaragoza"]),
    ("🇵🇹 Portugal",     "portugal",    ["portugal","lisbon","lisboa","porto","braga","coimbra","faro"]),
    ("🇮🇹 Italy",        "italy",       ["italy","italia","milan","milano","rome","roma","turin","torino","florence","firenze","bologna","naples","napoli"]),
    ("🇧🇪 Belgium",      "belgium",     ["belgium","belgique","brussels","bruxelles","antwerp","antwerpen","ghent","gent","bruges","liège"]),
    ("🇦🇹 Austria",      "austria",     ["austria","österreich","vienna","wien","graz","linz","salzburg","innsbruck"]),
    ("🇨🇭 Switzerland",  "switzerland", ["switzerland","schweiz","zurich","zürich","geneva","genève","bern","basel","lausanne"]),
    ("🇵🇱 Poland",       "poland",      ["poland","polska","warsaw","warszawa","krakow","kraków","wroclaw","wrocław","gdansk","gdańsk","poznan","poznań","lodz","łódź"]),
    ("🇨🇿 Czechia",      "czechia",     ["czech republic","czechia","prague","praha","brno","ostrava"]),
    ("🇷🇴 Romania",      "romania",     ["romania","românia","bucharest","bucurești","cluj","timisoara","iași","iasi"]),
    ("🇭🇺 Hungary",      "hungary",     ["hungary","magyarország","budapest","debrecen","pécs"]),
    ("🇬🇷 Greece",       "greece",      ["greece","ελλάδα","athens","αθήνα","thessaloniki","patras"]),
    ("🇧🇬 Bulgaria",     "bulgaria",    ["bulgaria","sofia","plovdiv","varna","burgas"]),
    ("🇭🇷 Croatia",      "croatia",     ["croatia","zagreb","split","rijeka","dubrovnik"]),
    ("🇸🇰 Slovakia",     "slovakia",    ["slovakia","bratislava","košice","prešov"]),
    ("🇸🇮 Slovenia",     "slovenia",    ["slovenia","ljubljana","maribor"]),
    ("🇪🇪 Estonia",      "estonia",     ["estonia","tallinn","tartu"]),
    ("🇱🇻 Latvia",       "latvia",      ["latvia","riga","daugavpils"]),
    ("🇱🇹 Lithuania",    "lithuania",   ["lithuania","vilnius","kaunas","klaipėda"]),
    ("🇱🇺 Luxembourg",   "luxembourg",  ["luxembourg"]),
    # ── UK ──
    ("🇬🇧 United Kingdom","uk",         ["united kingdom","uk","england","scotland","wales","london","manchester","edinburgh","birmingham","bristol","leeds","glasgow","cambridge","oxford","liverpool","sheffield","nottingham","newcastle","reading","brighton"]),
    # ── Asia-Pacific (visa-friendly) ──
    ("🇯🇵 Japan",        "japan",       ["japan","日本","tokyo","東京","osaka","大阪","kyoto","京都","yokohama","横浜","nagoya","名古屋","sapporo","札幌","fukuoka","福岡","kobe","神戸"]),
    ("🇸🇬 Singapore",    "singapore",   ["singapore","singapura","sg"]),
    ("🇹🇭 Thailand",     "thailand",    ["thailand","ประเทศไทย","bangkok","กรุงเทพ","chiang mai","เชียงใหม่","phuket","ภูเก็ต"]),
    ("🇲🇾 Malaysia",     "malaysia",    ["malaysia","malaysia","kuala lumpur","kl","penang","johor bahru","cyberjaya","petaling jaya"]),
    ("🇰🇷 South Korea",  "southkorea",  ["south korea","korea","한국","seoul","서울","busan","부산","incheon","인천"]),
    ("🇮🇩 Indonesia",    "indonesia",   ["indonesia","jakarta","bali","bandung","surabaya"]),
    ("🇻🇳 Vietnam",      "vietnam",     ["vietnam","việt nam","ho chi minh","hồ chí minh","hanoi","hà nội","da nang","đà nẵng"]),
    ("🇵🇭 Philippines",  "philippines", ["philippines","pilipinas","manila","maynila","cebu","davao"]),
    ("🇦🇺 Australia",    "australia",   ["australia","sydney","melbourne","brisbane","perth","adelaide","canberra"]),
    # ── Middle East (visa-friendly) ──
    ("🇦🇪 UAE / Dubai",  "uae",         ["uae","united arab emirates","dubai","دبي","abu dhabi","أبوظبي","sharjah"]),
    # ── Canada ──
    ("🇨🇦 Canada",       "canada",      ["canada","toronto","vancouver","montreal","ottawa","calgary","edmonton","winnipeg","québec","waterloo"]),
    # ── Remote ──
    ("🌍 Remote / Global","remote",     ["remote","worldwide","global","anywhere","distributed","work from anywhere","wfa"]),
]

# Flat list used for scan-time matching (all terms from all groups)
TARGET_LOCATIONS = [term for _, _, terms in COUNTRY_GROUPS for term in terms] + [
    "europe", "eu", "emea", "eea", "apac", "sea",
]

# Lookup: group_key -> list of match terms  (used by API filter)
COUNTRY_GROUP_MAP = {key: terms for _, key, terms in COUNTRY_GROUPS}

# ── Visa / Relocation keywords ────────────────────────────────────────────────
VISA_KEYWORDS = [
    "visa sponsorship", "visa sponsor", "will sponsor", "we sponsor",
    "can sponsor", "able to sponsor", "open to sponsor",
    "work permit", "work authorization", "work authorisation",
    "immigration support", "immigration assistance",
    "sponsorship available", "sponsorship considered",
    "global mobility", "right to work support",
    "tier 2", "tier2", "skilled worker visa",
    "h-1b", "h1b", "tss visa", "intra-company transfer",
]

RELOCATION_KEYWORDS = [
    "relocation", "relocation support", "relocation assistance",
    "relocation package", "relocation stipend", "relocation bonus",
    "moving allowance", "moving expenses", "moving support",
    "we help you move", "global mobility", "we'll help you relocate",
]

# ── Greenhouse ────────────────────────────────────────────────────────────────
# These are the EXACT company slugs used in Greenhouse's public API.
# URL pattern: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
GREENHOUSE_COMPANIES = [
    # Data / Analytics tools
    "dbt-labs", "fivetran", "airbyte", "hightouch", "getcensus",
    "lightdash", "metabase", "sigma-computing", "thoughtspot",
    "montecarlo", "atlan", "datafold", "sifflet",
    # Cloud / Infra
    "hashicorp", "cockroachdb", "planetscale", "supabase",
    "netlify", "vercel", "render", "fly",
    "launchdarkly", "sentry", "snyk", "1password",
    # Product / Analytics SaaS
    "amplitude", "mixpanel", "heap", "fullstory",
    "segment", "rudderstack", "june",
    # Growth / Marketing SaaS
    "klaviyo", "iterable", "braze", "customerio",
    # Dev tools
    "linear", "retool", "airplane", "airplane-dev",
    "coda", "notion", "airtable",
    # Fintech
    "brex", "ramp", "mercury", "gusto", "rippling",
    "stripe", "adyen",
    # Other high-growth
    "figma", "loom", "miro", "asana", "intercom",
    "zendesk", "hubspot", "drift", "gong",
    "benchling", "scale-ai", "cohere",
    "opentable", "doordash", "instacart",
    "airbnb", "lyft", "waymo",
    "datadog", "elastic", "grafana",
    "mongodb", "redis", "clickhouse",
    "starburst", "dremio", "imply",
    "contentful", "sanity", "storyblok",
    "mapbox", "here",
    "optimizely", "vwo",
    "brainly", "duolingo", "coursera",
    "procore", "toast", "zenoti",
    "shopify", "bigcommerce",
]

# ── Lever ─────────────────────────────────────────────────────────────────────
# URL pattern: https://api.lever.co/v0/postings/{slug}?mode=json
LEVER_COMPANIES = [
    "reddit", "coinbase", "robinhood", "chime",
    "palantir", "anduril",
    "duolingo", "coursera", "procore", "toast",
    "typeform", "pendo", "surveymonkey",
    "grafana-labs", "gitlab", "sourcegraph",
    "figma", "framer",
    "netlify", "cloudflare",
    "asana", "notion",
    "vercel", "fly-io",
    "scale-ai", "labelbox",
    "stripe", "plaid", "marqeta",
    "benchling", "genentech",
    "openai", "deepmind",
    "canva", "miro",
    "shopify", "faire",
    "flexport", "convoy",
    "nerdwallet", "chime",
    "ro", "hims",
    "brex", "ramp",
]

# ── Ashby ─────────────────────────────────────────────────────────────────────
# URL pattern: https://api.ashbyhq.com/posting-api/job-board/{slug}
ASHBY_COMPANIES = [
    "anthropic", "together-ai", "mistral", "cohere",
    "baseten", "modal", "replicate", "hugging-face",
    "anyscale", "ray", "lightning-ai",
    "ramp", "mercury", "brex",
    "cal-com", "cal",
    "neon", "turso", "xata",
    "trigger-dev", "inngest",
    "resend", "loops",
    "vercel", "railway",
    "liveblocks", "partykit",
    "rows", "grist",
    "dub", "documenso",
    "infisical", "doppler",
    "supabase", "nhost",
    "plane", "twenty",
    "formbricks", "cal",
    "highlight", "posthog",
    "growthbook",
]

# ── Workable ──────────────────────────────────────────────────────────────────
# URL pattern: https://{slug}.workable.com/spi/v3/jobs
WORKABLE_COMPANIES = [
    "revolut", "monzo", "starling-bank", "starling",
    "transferwise", "wise",
    "deliveroo", "ocado-technology", "ocado",
    "skyscanner", "booking",
    "criteo", "deezer", "blablacar",
    "productboard", "contentsquare",
    "algolia", "doctolib", "leboncoin",
    "personio", "pleo", "spendesk",
    "moonpig", "cazoo", "motorway",
    "gousto", "oddbox", "oddbox-ltd",
    "depop", "vinted",
    "checkout", "checkout-com",
    "railsbank", "currencycloud",
    "tractable", "wayve",
    "improbable", "hadean",
    "onfido", "jumio",
    "paddle", "chargebee",
    "thought-machine", "mambu",
    "multiverse", "springpod",
    "tessian", "darktrace",
]

# ── SmartRecruiters ───────────────────────────────────────────────────────────
# URL pattern: https://api.smartrecruiters.com/v1/companies/{slug}/postings
SMARTRECRUITERS_COMPANIES = [
    "Bosch", "HiltonWorldwide", "ALDI", "Lidl", "Zalando",
    "N26", "HelloFresh", "GetYourGuide",
    "Adidas", "AboutYou", "Westwing",
    "MediaMarktSaturn", "Otto",
    "Delivery-Hero", "DeliveryHero",
    "Klarna", "Bamboocard",
    "Volocopter", "Lilium",
    "AUTO1Group", "Heycar",
    "Flixbus", "FlixMobility",
    "Omio", "Trainline",
]

# ── BreezyHR ──────────────────────────────────────────────────────────────────
# URL pattern: https://{slug}.breezy.hr/json
BREEZY_COMPANIES = [
    "doist", "todoist",
    "automattic", "wordpress",
    "wikimedia",
    "remote", "remote-com",
    "close", "close-crm",
    "basecamp", "37signals",
    "buffer",
    "ghost",
    "balsamiq",
    "carto",
]

# ── Recruitee ─────────────────────────────────────────────────────────────────
# URL pattern: https://{slug}.recruitee.com/api/offers/
RECRUITEE_COMPANIES = [
    "framer", "pitch",
    "rows", "grist-labs",
    "missive", "superhuman",
    "loom", "mmhmm",
    "retool",
    "linear",
    "nansen",
    "dune-analytics",
]

# ── Teamtailor ────────────────────────────────────────────────────────────────
# URL pattern: https://api.teamtailor.com/v1/jobs?filter[company]={slug}
TEAMTAILOR_COMPANIES = [
    "klarna", "king",
    "hemnet", "tink",
    "trustly", "izettle",
    "qapital", "betterment",
    "northmill", "hive",
    "karma", "loanstep",
    "matsmart", "re-lean",
]

# ── Jobvite ───────────────────────────────────────────────────────────────────
# URL pattern: https://jobs.jobvite.com/api/company/{slug}/jobs
JOBVITE_COMPANIES = [
    "surveymonkey", "zuora",
    "elastic", "talend",
    "veeva", "medidata",
    "informatica", "tibco",
]

# ── BambooHR ──────────────────────────────────────────────────────────────────
# URL pattern: https://{slug}.bamboohr.com/careers/list?format=json
BAMBOOHR_COMPANIES = [
    "qualtrics", "instructure",
    "domo", "clearbit",
    "divvy", "lucid",
    "chatsworth", "podium",
    "weave", "chatsworth",
    "healthequity", "workfront",
]

# ── Workday ───────────────────────────────────────────────────────────────────
# Format: (company_subdomain, tenant_id)
WORKDAY_TENANTS = [
    ("amazon",      "amazon"),
    ("google",      "google"),
    ("microsoft",   "msft"),
    ("apple",       "apple"),
    ("meta",        "meta"),
    ("sap",         "sap"),
    ("oracle",      "oracle"),
    ("salesforce",  "salesforce"),
    ("servicenow",  "servicenow"),
    ("workday",     "workday"),
    ("adidas",      "adidas"),
    ("nike",        "nike"),
    ("booking",     "booking"),
    ("spotify",     "spotify"),
    ("netflix",     "netflix"),
    ("uber",        "uber"),
    ("airbnb",      "airbnb"),
    ("linkedin",    "linkedin"),
    ("twitter",     "twitter"),
    ("snap",        "snap"),
]

# ── HTTP ──────────────────────────────────────────────────────────────────────
REQUEST_TIMEOUT = 15
REQUEST_DELAY   = 0.2
MAX_RETRIES     = 2
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
}

MAX_JOB_AGE_DAYS = 5

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DATA_DIR        = os.path.join(BASE_DIR, "data")
JOBS_CACHE_FILE = os.path.join(DATA_DIR, "jobs_cache.json")
SCAN_META_FILE  = os.path.join(DATA_DIR, "scan_meta.json")
os.makedirs(DATA_DIR, exist_ok=True)
