import requests
import sqlite3

API_ENDPOINT = "https://uncovering-cicada.fandom.com/api.php"

session = requests.session()

def login(bot_username, bot_password): # Get yours over at https://uncovering-cicada.fandom.com/wiki/Special:BotPasswords
  r = session.get(API_ENDPOINT, params={
    "action": "query",
    "format": "json",

    "meta": "tokens",
    "type": "login"
  })
  login_token = r.json()['query']['tokens']['logintoken']

  r = session.post(API_ENDPOINT, data={
    "action": "login",
    "format": "json",

    "lgname": bot_username,
    "lgpassword": bot_password,
    "lgtoken": login_token
  })
  assert r

  r = session.get(API_ENDPOINT, params={
    "action": "query",
    "format": "json",

    "meta": "tokens"
  })
  csrf_token = r.json()['query']['tokens']['csrftoken']

  return csrf_token

# create a bot account over at: https://uncovering-cicada.fandom.org/wiki/Special:BotPassword
crsf_token = login('Username@botname', 'botpassword')

def full_list(queried_field, params={}):
  def make_request(continue_info=None):
    complete_params = {
      "action": "query",
      "format": "json"
    }
    complete_params.update(params)

    if continue_info:
      complete_params.update(continue_info)

    r = session.get(API_ENDPOINT, params=complete_params)
    return r.json()

  continue_info = None
  first_request = True
  while continue_info or first_request:
    data = make_request(continue_info)

    queried = data["query"][queried_field]
    if isinstance(queried, dict):
      yield from queried.items()
    else:
      for event in queried:
        yield event

    continue_info = data.get("continue", None)
    first_request = False

def get_rev(id):
  def to_sequence(l):
    return "|".join(map(str, l))

  return full_list("pages", params={
    "prop": "revisions",
    "rvprop": "content",
    "rvslots": "*",
    "revids": id
#    revids": to_sequence(ids)
  })
def get_deleted_rev(id):
  def to_sequence(l):
    return "|".join(map(str, l))

  return full_list("pages", params={
    "prop": "deletedrevisions",
    "drvprop": "content",
    "drvslots": "*",
    "revids": id
#    "revids": to_sequence(ids)
  })

# Storage database
con = sqlite3.connect('wiki.db')
cur = con.cursor()

# revisions:
#  - revid: revision id, the same to what's used on Fandom
#  - author: username of the revision author
#  - page: page title
#  - timestamp: timestamp of the revision, as a ISO8601 strings ("YYYY-MM-DD HH:MM:SS.SSS")
#  - comment
#  - content
#  - status: 'A' for active revision, 'D' for deleted revision
cur.execute("""
CREATE TABLE IF NOT EXISTS revisions (
  fandom_id INTEGER PRIMARY KEY,
  author INTEGER,
  page INTEGER,
  timestamp TEXT,
  comment TEXT,
  content TEXT,

  status TEXT
)
""")

deleted_ids = []
for deleted_rev_of in full_list("alldeletedrevisions", params={
      "list": "alldeletedrevisions",

      "adrlimit": 500,
      "adrdir": "older"
    }):
  # deleted_rev_of: all deleted revisions on a given page. This page can be itself deleted

  # page_id == 0 when the page has been deleted
  page_id = deleted_rev_of["pageid"]
  page_name = deleted_rev_of["title"]
  page_namespace = deleted_rev_of["ns"]

  deleted_revisions = deleted_rev_of["revisions"]
  for deleted_revision in deleted_revisions:
    if "userhidden" in deleted_revision:
      print(f"Deleted revision {deleted_revision['revid']} deleted")
      continue

    revision_id = deleted_revision["revid"]
    revision_author = deleted_revision["user"]
    revision_timestamp = deleted_revision["timestamp"].replace('T', ' ').replace('Z', '')
    revision_comment = deleted_revision["comment"]

    cur.execute("INSERT INTO revisions (fandom_id, author, page, timestamp, comment, content, status) VALUES (?, ?, ?, ?, ?, ?, 'A')",
     (revision_id, revision_author, page_name, revision_timestamp, revision_comment, "")) # dummy content for now
    deleted_ids.append(revision_id)
#print(deleted_ids)

active_ids = []
for active_rev_of in full_list("allrevisions", params={
      "list": "allrevisions",

      "arvlimit": 500,
      "arvdir": "older"
    }):
  # active_rev_of: all deleted revisions on a given page. This page can be itself deleted

  page_id = active_rev_of["pageid"]
  assert page_id != 0
  page_name = active_rev_of["title"]
  page_namespace = active_rev_of["ns"]

  active_revisions = active_rev_of["revisions"]
  for active_revision in active_revisions:
    if "userhidden" in deleted_revision:
      print(f"Active revision {deleted_revision['revid']} deleted")
      continue

    revision_id = active_revision["revid"]
    revision_author = active_revision["user"]
    revision_timestamp = active_revision["timestamp"].replace('T', ' ').replace('Z', '')
    revision_comment = active_revision["comment"]

    cur.execute("INSERT INTO revisions (fandom_id, author, page, timestamp, comment, content, status) VALUES (?, ?, ?, ?, ?, ?, 'D')",
     (revision_id, revision_author, page_name, revision_timestamp, revision_comment, "")) # dummy content for now
    active_ids.append(revision_id)
#print(active_ids)

print("Adding content...")

# Adding content
for revision_id in deleted_ids:
  print(revision_id)

  revision_data = next(get_deleted_rev(revision_id))[1]
  slots = revision_data["deletedrevisions"][0]["slots"]

  slots_names = slots.keys()
  if list(slots_names) != ["main"]:
    print(slots)

  content = slots["main"]['*']
  con.execute("UPDATE revisions SET content = ? WHERE fandom_id = ?", (content, revision_id))

for revision_id in active_ids:
  print(revision_id)

  revision_data = next(get_rev(revision_id))[1]
  slots = revision_data["revisions"][0]["slots"]

  slots_names = slots.keys()
  if list(slots_names) != ["main"]:
    print(slots)

  content = slots["main"]['*']
  con.execute("UPDATE revisions SET content = ? WHERE fandom_id = ?", (content, revision_id))

con.commit()
