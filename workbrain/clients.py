"""Read-only API clients. No API mutation methods are exposed."""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .storage import BrainError


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a bearer token to a redirect destination.
        return None


class API:
    def __init__(self, base, token, provider, opener=None, sleep=time.sleep):
        parsed = urllib.parse.urlsplit(base)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise BrainError("API base must be HTTPS, without credentials, query, or fragment.")
        self.base = base.rstrip("/")
        self.provider = provider
        self.headers = {"Accept": "application/json", "User-Agent": "work-brain/0.1"}
        if provider == "asana":
            self.headers["Authorization"] = "Bearer " + token
        else:
            self.headers["PRIVATE-TOKEN"] = token
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.sleep = sleep

    def get(self, path, params=None):
        url = path if path.startswith("https://") else self.base + path
        # GitLab pagination links may be absolute, but must stay inside the API base.
        if not url.startswith(self.base + "/"):
            raise BrainError("Refused pagination URL outside the configured API base.")
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers=self.headers, method="GET")
                with self.opener.open(req, timeout=30) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    if isinstance(data, dict) and data.get("errors"):
                        raise BrainError(f"{self.provider}: API returned errors; previous snapshot kept.")
                    return data, response.headers
            except urllib.error.HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise BrainError(f"{self.provider}: HTTP {error.code}; response body withheld.") from None
                try:
                    delay = float(error.headers.get("Retry-After", 2 ** attempt))
                except (ValueError, TypeError):
                    delay = 2 ** attempt
                if delay > 30:
                    raise BrainError(f"{self.provider}: rate limited; retry later. Previous snapshot kept.") from None
                self.sleep(max(0, delay))
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == 2:
                    raise BrainError(f"{self.provider}: network request failed; check connection.") from None
                self.sleep(2 ** attempt)
            except (ValueError, UnicodeError):
                raise BrainError(f"{self.provider}: invalid JSON response; previous snapshot kept.") from None
        raise BrainError("Request retry limit reached.")

    def one(self, path, params=None):
        data, _ = self.get(path, params)
        return data["data"] if self.provider == "asana" else data

    def all(self, path, params=None):
        params = dict(params or {})
        params.setdefault("limit" if self.provider == "asana" else "per_page", 100)
        rows, visited = [], set()
        for _ in range(1000):
            marker = (path, json.dumps(params, sort_keys=True))
            if marker in visited:
                raise BrainError(f"{self.provider}: pagination repeated; incomplete results rejected.")
            visited.add(marker)
            data, headers = self.get(path, params)
            page = data.get("data") if self.provider == "asana" else data
            if not isinstance(page, list):
                raise BrainError(f"{self.provider}: unexpected list response.")
            rows.extend(page)
            if self.provider == "asana":
                next_page = data.get("next_page")
                if not next_page:
                    return rows
                if not next_page.get("offset"):
                    raise BrainError("asana: next page has no offset.")
                params["offset"] = next_page["offset"]
            else:
                match = re.search(r'<([^>]+)>;\s*rel="next"', headers.get("Link", ""))
                if match:
                    path, params = match.group(1), {}
                elif headers.get("X-Next-Page"):
                    params["page"] = headers["X-Next-Page"]
                else:
                    return rows
        raise BrainError(f"{self.provider}: pagination limit exceeded; incomplete results rejected.")


TASK_FIELDS = "tags.gid,name,notes,completed,assignee.name,due_on,modified_at,num_subtasks,parent.name,permalink_url"


def task_tree(api, project_id=None, roots=()):
    """Include nested subtasks and deduplicate tasks also present at project level."""
    params = {"opt_fields": TASK_FIELDS}
    todo = api.all(f"/projects/{project_id}/tasks", params) if project_id else []
    todo.extend(api.one(f"/tasks/{gid}", params) for gid in roots)
    seen = {}
    while todo:
        task = todo.pop(0)
        gid = task["gid"]
        if gid in seen:
            continue
        seen[gid] = task
        if len(seen) > 100000:
            raise BrainError("Task tree exceeded safety limit; snapshot not replaced.")
        if task.get("num_subtasks", 0):
            todo.extend(api.all(f"/tasks/{gid}/subtasks", params))
    return list(seen.values())
