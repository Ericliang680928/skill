#!/usr/bin/env python3
"""Minimal ComfyUI HTTP API client (stdlib only)."""
import argparse, json, mimetypes, os, re, sys, time, uuid
import urllib.request, urllib.parse, urllib.error


def req(url, data=None, headers=None, method=None):
    r = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from {url}: {e.read().decode(errors='replace')[:2000]}")
    except urllib.error.URLError as e:
        sys.exit(f"Cannot reach {url}: {e.reason}")


def get_json(base, path):
    return json.loads(req(base + path))


def cmd_check(a):
    s = get_json(a.base, "/system_stats")
    print(json.dumps(s.get("system", s), indent=2, ensure_ascii=False))


def cmd_nodes(a):
    info = get_json(a.base, "/object_info")
    if a.detail:
        n = info.get(a.keyword)
        if not n:
            sys.exit(f"No node class '{a.keyword}'")
        print(json.dumps(n, indent=2, ensure_ascii=False))
        return
    kw = a.keyword.lower()
    hits = [k for k, v in info.items()
            if kw in k.lower() or kw in (v.get("display_name") or "").lower()
            or kw in (v.get("category") or "").lower()]
    for k in sorted(hits):
        v = info[k]
        print(f"{k}\t{v.get('display_name','')}\t[{v.get('category','')}]")
    if not hits:
        print("(no match)")


def cmd_upload(a):
    path = a.file
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    body = b""
    for k, v in (("type", "input"), ("overwrite", "true")):
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
             f'filename="{os.path.basename(path)}"\r\nContent-Type: {ctype}\r\n\r\n').encode()
    body += open(path, "rb").read() + f"\r\n--{boundary}--\r\n".encode()
    out = json.loads(req(a.base + "/upload/image", body,
                         {"Content-Type": f"multipart/form-data; boundary={boundary}"}))
    print(out["name"])


def subst(obj, vals):
    if isinstance(obj, dict):
        return {k: subst(v, vals) for k, v in obj.items()}
    if isinstance(obj, list):
        return [subst(v, vals) for v in obj]
    if isinstance(obj, str):
        for k, v in vals.items():
            tok = "{{%s}}" % k
            if obj == tok:  # whole value -> keep native type (int/float)
                return v
            obj = obj.replace(tok, str(v))
    return obj


def queue(base, wf, client_id):
    r = json.loads(req(base + "/prompt",
                       json.dumps({"prompt": wf, "client_id": client_id}).encode(),
                       {"Content-Type": "application/json"}))
    if r.get("node_errors"):
        sys.exit("Node errors: " + json.dumps(r["node_errors"], indent=2, ensure_ascii=False))
    return r["prompt_id"]


class JobError(Exception):
    pass


def wait(base, pid, poll=5, timeout=3600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = get_json(base, f"/history/{pid}")
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                raise JobError(f"Job {pid} failed: {json.dumps(msgs, ensure_ascii=False)[:2000]}")
            return h[pid]
        time.sleep(poll)
    raise JobError(f"Timeout waiting for {pid}")


def download_outputs(base, hist, outdir, index):
    os.makedirs(outdir, exist_ok=True)
    saved = []
    for node_out in hist.get("outputs", {}).values():
        for key in ("videos", "gifs", "images", "audio"):
            for f in node_out.get(key, []):
                if f.get("type") == "temp":  # previews, not final outputs
                    continue
                q = urllib.parse.urlencode({"filename": f["filename"],
                                            "subfolder": f.get("subfolder", ""),
                                            "type": f.get("type", "output")})
                dst = os.path.join(outdir, f"shot{index:02d}_{os.path.basename(f['filename'])}")
                with open(dst, "wb") as fh:
                    fh.write(req(base + "/view?" + q))
                saved.append(dst)
    return saved


def cmd_submit(a):
    wf = json.load(open(a.workflow))
    pid = queue(a.base, wf, uuid.uuid4().hex)
    print("prompt_id", pid)
    if a.wait:
        try:
            print("\n".join(download_outputs(a.base, wait(a.base, pid), a.out, 0)))
        except JobError as e:
            sys.exit(str(e))


PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def cmd_fanout(a):
    tpl = json.load(open(a.template))
    plan = json.load(open(a.plan))
    only = {int(x) for x in a.only.split(",")} if a.only else None
    cid = uuid.uuid4().hex
    jobs = []  # (index, prompt_id, vals)
    for s in plan["shots"]:
        i = s["index"]
        if only and i not in only:
            continue
        if not s.get("prompt"):
            sys.exit(f"Shot {i} has no prompt in {a.plan}")
        vals = {"image": a.image, "audio": a.audio or "", "prompt": s["prompt"],
                "duration": s["duration"], "seed": s.get("seed", 1000 + i),
                "index": i, "prefix": f"mv_shot{i:02d}"}
        wf = subst(tpl, vals)
        left = set(PLACEHOLDER.findall(json.dumps(wf)))
        if left:
            sys.exit(f"Unresolved placeholders in template: {sorted(left)}")
        if a.dry_run:
            print(f"--- shot {i} ---\n{json.dumps(wf, indent=2, ensure_ascii=False)}")
            continue
        pid = queue(a.base, wf, cid)
        print(f"shot {i}: queued {pid} ({s['duration']}s)", flush=True)
        jobs.append((i, pid, vals))
    if a.dry_run:
        return
    with open(a.jobs, "w") as fh:  # lets `collect` resume if this process dies
        json.dump([{"index": i, "prompt_id": pid} for i, pid, _ in jobs], fh)
    if not a.wait:
        print(f"Queued {len(jobs)} jobs; fetch later with: collect {a.jobs}")
        return
    failed = []
    for i, pid, vals in jobs:
        for attempt in (0, 1):
            try:
                files = download_outputs(a.base, wait(a.base, pid), a.out, i)
                print(f"shot {i}: done -> {files}", flush=True)
                break
            except JobError as e:
                print(f"shot {i}: {e}", file=sys.stderr, flush=True)
                if attempt or not a.retry:
                    failed.append(i)
                    break
                vals["seed"] += 1000  # retry once with a fresh seed
                pid = queue(a.base, subst(tpl, vals), cid)
                print(f"shot {i}: retry queued {pid}", flush=True)
    if failed:
        sys.exit(f"Failed shots: {failed}. Re-run with --only {','.join(map(str, failed))}")


def cmd_collect(a):
    failed = []
    for j in json.load(open(a.jobs)):
        try:
            files = download_outputs(a.base, wait(a.base, j["prompt_id"]), a.out, j["index"])
            print(f"shot {j['index']}: done -> {files}", flush=True)
        except JobError as e:
            print(f"shot {j['index']}: {e}", file=sys.stderr)
            failed.append(j["index"])
    if failed:
        sys.exit(f"Failed shots: {failed}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", required=True, help="ComfyUI base URL, e.g. http://127.0.0.1:8188")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("check").set_defaults(f=cmd_check)
    n = sp.add_parser("nodes"); n.add_argument("keyword")
    n.add_argument("--detail", action="store_true", help="treat keyword as exact class name"); n.set_defaults(f=cmd_nodes)
    u = sp.add_parser("upload"); u.add_argument("file"); u.set_defaults(f=cmd_upload)
    s = sp.add_parser("submit"); s.add_argument("workflow"); s.add_argument("--wait", action="store_true")
    s.add_argument("--out", default="out"); s.set_defaults(f=cmd_submit)
    f = sp.add_parser("fanout"); f.add_argument("template"); f.add_argument("plan")
    f.add_argument("--image", required=True); f.add_argument("--audio")
    f.add_argument("--only", help="comma list of shot indexes"); f.add_argument("--wait", action="store_true")
    f.add_argument("--out", default="clips"); f.add_argument("--jobs", default="jobs.json")
    f.add_argument("--dry-run", action="store_true", help="print substituted workflows, queue nothing")
    f.add_argument("--no-retry", dest="retry", action="store_false", help="don't retry failed shots")
    f.set_defaults(f=cmd_fanout)
    c = sp.add_parser("collect", help="wait for + download jobs listed in jobs.json")
    c.add_argument("jobs", nargs="?", default="jobs.json"); c.add_argument("--out", default="clips")
    c.set_defaults(f=cmd_collect)
    a = p.parse_args()
    a.base = a.url.rstrip("/")
    a.f(a)


if __name__ == "__main__":
    main()
