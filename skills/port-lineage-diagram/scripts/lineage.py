#!/usr/bin/env python3
"""Validate and render field-port workflow diagrams. Python 3.10+, stdlib only.

Never executes field rules or reads files named in evidence strings.
"""
from __future__ import annotations
import argparse
import collections
import html
import json
import math
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

VERSION = "1.0.0"
ROOT_KINDS = {"input", "database", "api", "file", "config", "constant", "runtime"}
OPS = {"root", "identity", "rename", "cast", "normalize", "derive", "lookup", "aggregate", "choose", "unknown"}
ROLES = {"value", "selector", "condition"}
OP_LABELS = {"root": "源", "identity": "透传", "rename": "更名", "cast": "转型", "normalize": "规范", "derive": "计算", "lookup": "查表", "aggregate": "聚合", "choose": "择支", "unknown": "待确认"}
COLORS = {"root": "#3976CF", "identity": "#3976CF", "rename": "#199681", "cast": "#199681", "normalize": "#199681", "derive": "#D38727", "lookup": "#9162C9", "aggregate": "#D38727", "choose": "#D38727", "unknown": "#C34556"}
NODE_COLORS = {"source": ("#EEF5FF", "#B9D0F2", "#3976CF"), "process": ("#EDFAF6", "#AADACD", "#168C76"), "reference": ("#F5EFFF", "#D8C5F0", "#9162C9"), "config": ("#F5EFFF", "#D8C5F0", "#9162C9"), "output": ("#FFF6E8", "#EACD9E", "#BC7A23")}
ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")

class ModelError(ValueError):
    pass

def dependencies(field: dict) -> list[dict]:
    return [{"ref": d, "role": "value"} if isinstance(d, str) else {"role": "value", **d} for d in field.get("from", [])]

def index_model(model: dict) -> tuple[dict, dict]:
    nodes = {n["id"]: n for n in model["nodes"]}
    fields = {f'{n["id"]}.{f["id"]}': {**f, "node": n["id"], "ref": f'{n["id"]}.{f["id"]}'} for n in model["nodes"] for f in n["fields"]}
    return nodes, fields

def trace(fields: dict, target: str) -> dict:
    """Compute exact ancestors and dependency edges; key by full field reference."""
    seen, roots, unknown, edges = set(), set(), set(), set()
    def walk(ref: str):
        if ref in seen:
            return
        seen.add(ref)
        f = fields[ref]
        if f.get("op") == "unknown":
            unknown.add(ref)
        if f.get("origin"):
            roots.add(ref)
        for d in dependencies(f):
            edges.add((d["ref"], ref, d["role"], d.get("when", "")))
            walk(d["ref"])
    walk(target)
    return {"fields": sorted(seen), "roots": sorted(roots), "unknown": sorted(unknown), "edges": sorted(edges)}

def validate(model: dict) -> dict:
    errors, warnings = [], []
    if not isinstance(model, dict):
        raise ModelError("Model must be a JSON object.")
    if model.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'.")
    if not isinstance(model.get("title"), str) or not model["title"].strip():
        errors.append("title must be a nonempty string.")
    if model.get("mode") not in {"example", "design", "grounded"}:
        errors.append("mode must be example, design, or grounded.")
    nodes = model.get("nodes", [])
    if not isinstance(nodes, list) or not nodes or not all(isinstance(n, dict) for n in nodes):
        raise ModelError("nodes must be a nonempty array of objects.")
    node_ids, refs = set(), set()
    for n in nodes:
        nid = n.get("id", "")
        if not isinstance(nid, str) or not ID_RE.fullmatch(nid) or nid in node_ids:
            errors.append(f"Invalid or duplicate node id: {nid!r}")
        node_ids.add(str(nid))
        if n.get("kind") not in NODE_COLORS:
            errors.append(f"{nid}: kind must be source/process/reference/config/output.")
        if not isinstance(n.get("label"), str) or not n["label"].strip():
            errors.append(f"{nid}: a human-readable label is required.")
        if not isinstance(n.get("fields"), list) or not n["fields"]:
            errors.append(f"{nid}: fields must be a nonempty array.")
            continue
        for f in n["fields"]:
            if not isinstance(f, dict):
                errors.append(f"{nid}: every field must be an object.")
                continue
            fid = f.get("id", "")
            ref = f"{nid}.{fid}"
            if not isinstance(fid, str) or not ID_RE.fullmatch(fid) or ref in refs:
                errors.append(f"Invalid or duplicate field id: {ref}")
            refs.add(ref)
            for key in ("label", "type"):
                if not isinstance(f.get(key), str) or not f[key].strip():
                    errors.append(f"{ref}: {key} is required.")
            if f.get("op") not in OPS:
                errors.append(f"{ref}: unsupported op {f.get('op')!r}.")
            raw_deps = f.get("from", [])
            if not isinstance(raw_deps, list) or any(not isinstance(d, (str, dict)) for d in raw_deps):
                errors.append(f"{ref}: from must be an array of refs or dependency objects.")
                continue
            deps = dependencies(f)
            origin = f.get("origin")
            if origin is not None and (not isinstance(origin, dict) or origin.get("kind") not in ROOT_KINDS or not origin.get("locator")):
                errors.append(f"{ref}: origin needs a legal kind and nonempty locator.")
            if f.get("op") == "root":
                if not origin or deps:
                    errors.append(f"{ref}: root must have origin and no dependencies.")
            elif f.get("op") == "unknown":
                if not f.get("note") or deps or origin:
                    errors.append(f"{ref}: unknown must have a note, no origin, no invented dependencies.")
                warnings.append(f"{ref}: origin is unresolved.")
            elif origin or not deps:
                errors.append(f"{ref}: non-root output requires explicit from; cannot also declare origin.")
            if f.get("op") in {"identity", "rename", "cast", "normalize"} and len(deps) != 1:
                errors.append(f"{ref}: {f.get('op')} requires exactly one dependency.")
            if f.get("op") not in {"root", "identity", "rename", "unknown"} and not f.get("rule"):
                errors.append(f"{ref}: transformation rule is required.")
            if f.get("op") == "choose" and (len(deps) < 2 or any(not d.get("when") for d in deps)):
                errors.append(f"{ref}: choose requires guarded candidate dependencies.")
            status = f.get("status", "declared")
            if status not in {"declared", "verified", "unknown"}:
                errors.append(f"{ref}: status must be declared/verified/unknown.")
            if status == "verified" and (not f.get("evidence") or model.get("mode") != "grounded"):
                errors.append(f"{ref}: verified needs evidence and grounded mode; examples cannot be verified.")
            for d in deps:
                if not isinstance(d.get("ref"), str) or d.get("role") not in ROLES:
                    errors.append(f"{ref}: invalid dependency ref/role.")
            for d in deps:
                if not isinstance(d.get("when", ""), str):
                    errors.append(f"{ref}: dependency when must be a string.")
            signatures = [(str(d.get("ref")), str(d.get("role")), str(d.get("when", ""))) for d in deps]
            if f.get("op") in {"identity", "rename"} and any(d["role"] != "value" for d in deps):
                errors.append(f"{ref}: identity/rename need a value dependency, not a selector/condition.")
            if len(signatures) != len(set(signatures)):
                errors.append(f"{ref}: duplicate dependency edge.")
        pos = n.get("position")
        if pos is not None and (not isinstance(pos, list) or len(pos) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in pos)):
            errors.append(f"{nid}: position must be [nonnegative x, nonnegative y].")
        width = n.get("width", 300)
        if isinstance(width, bool) or not isinstance(width, (int, float)) or not math.isfinite(width) or not 240 <= width <= 900:
            errors.append(f"{nid}: width must be between 240 and 900 pixels.")
    def point_ok(p):
        return isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int,float)) and not isinstance(v,bool) and math.isfinite(v) and v >= 0 for v in p)
    if not isinstance(model.get("routes", {}), dict):
        errors.append("routes must be an object mapping source->target to waypoint arrays.")
    else:
        for key, points in model.get("routes", {}).items():
            if not isinstance(points, list) or not all(point_ok(p) for p in points):
                errors.append(f"{key}: route waypoints must be nonnegative [x,y] pairs.")
    for ann in model.get("annotations", []):
        if not isinstance(ann,dict) or not point_ok([ann.get("x"),ann.get("y")]) or not isinstance(ann.get("text"),str):
            errors.append("Annotation needs numeric x/y and text.")
        elif not isinstance(ann.get("size",12), (int,float)) or not 8 <= ann.get("size",12) <= 40:
            errors.append("Annotation size must be between 8 and 40.")
    if errors:
        raise ModelError("\n".join(errors))
    ns, fs = index_model(model)
    for ref, f in fs.items():
        for d in dependencies(f):
            if d["ref"] not in fs:
                errors.append(f"{ref}: dependency does not exist: {d['ref']}")
            elif f["op"] in {"identity", "rename"} and d["role"] == "value" and fs[d["ref"]]["type"] != f["type"]:
                errors.append(f"{ref}: {f['op']} must preserve type; use cast instead.")
    for e in model.get("controls", []):
        if e.get("from") not in ns or e.get("to") not in ns:
            errors.append("Control edge refers to an unknown node.")
        if not e.get("label"):
            errors.append("Control edges need an explicit label/condition.")
    if errors:
        raise ModelError("\n".join(errors))
    state = {}
    def visit(ref, stack):
        if state.get(ref) == 1:
            raise ModelError("Data dependency cycle: " + " -> ".join(stack + [ref]) + ". Model previous/next iteration as separate versioned fields; do not delete the edge.")
        if state.get(ref) == 2:
            return
        state[ref] = 1
        for d in dependencies(fs[ref]):
            visit(d["ref"], stack + [ref])
        state[ref] = 2
    for ref in fs:
        visit(ref, [])
    outputs = model.get("outputs", [r for r, f in fs.items() if ns[f["node"]]["kind"] == "output"])
    if not isinstance(outputs, list) or not outputs or any(r not in fs for r in outputs) or len(outputs) != len(set(outputs)):
        raise ModelError("outputs must be a nonempty unique array of existing full field refs.")
    if model.get("default_field", outputs[-1]) not in fs:
        raise ModelError("default_field must reference an existing field.")
    connected = {d["ref"] for f in fs.values() for d in dependencies(f)} | set(outputs)
    for r in fs:
        if r not in connected:
            warnings.append(f"{r}: unused field; remove if outside scope, or explain intentional retention.")
    covered, verified = [], []
    traces = {}
    for out in outputs:
        t = trace(fs, out)
        traces[out] = t
        if not t["unknown"] and t["roots"]:
            covered.append(out)
            if all(fs[r].get("status") == "verified" and fs[r].get("evidence") for r in t["fields"]):
                verified.append(out)
    all_pos = [n.get("position") is not None for n in nodes]
    if any(all_pos) and not all(all_pos):
        raise ModelError("Provide position for all nodes or none; partial layout hints are ambiguous.")
    return {"valid": True, "mode": model["mode"], "nodes": len(ns), "fields": len(fs), "dependency_edges": sum(len(dependencies(f)) for f in fs.values()), "outputs": outputs, "covered_outputs": covered, "verified_outputs": verified, "warnings": warnings, "traces": traces}

def text_width(s: str, px: float) -> float:
    return sum(1 if unicodedata.east_asian_width(c) in "WF" else .58 for c in str(s)) * px

def fit(s: str, width: float, px: float) -> str:
    s = str(s)
    if text_width(s, px) <= width:
        return s
    result = ""
    for c in s:
        if text_width(result + c + "…", px) > width:
            break
        result += c
    return result + "…"

HEADER, ROW = 95, 70

def layout(model: dict) -> dict:
    ns, fs = index_model(model)
    boxes = {n["id"]: {"w": n.get("width", 300), "h": HEADER + len(n["fields"]) * ROW + 18} for n in model["nodes"]}
    if all("position" in n for n in model["nodes"]):
        for n in model["nodes"]:
            boxes[n["id"]].update(x=n["position"][0], y=n["position"][1])
        return boxes
    incoming = {n: set() for n in ns}
    for f in fs.values():
        for d in dependencies(f):
            a, b = fs[d["ref"]]["node"], f["node"]
            if a != b:
                incoming[b].add(a)
    rank, pending = {}, set(ns)
    while pending:
        ready = [n for n in ns if n in pending and incoming[n] <= rank.keys()]
        if not ready:
            raise ModelError("Node-level data graph is cyclic. Unroll iterations or provide an explicit, reviewed layout; the renderer never drops dependencies.")
        for n in ready:
            rank[n] = max((rank[p] + 1 for p in incoming[n]), default=0)
            pending.remove(n)
    groups = collections.defaultdict(list)
    for n in ns:
        groups[rank[n]].append(n)
    maxh = max(sum(boxes[n]["h"] for n in group) + 100 * (len(group)-1) for group in groups.values())
    x = 40
    for r in sorted(groups):
        group = groups[r]
        h = sum(boxes[n]["h"] for n in group) + 100*(len(group)-1)
        y = 120 + (maxh-h)/2
        for n in group:
            boxes[n].update(x=x, y=y)
            y += boxes[n]["h"] + 100
        x += max(boxes[n]["w"] for n in group) + 140
    return boxes

def geometry_issues(boxes: dict) -> list[str]:
    issues = []
    for a, ba in boxes.items():
        for b, bb in boxes.items():
            if a >= b:
                continue
            if ba["x"] < bb["x"]+bb["w"] and bb["x"] < ba["x"]+ba["w"] and ba["y"] < bb["y"]+bb["h"] and bb["y"] < ba["y"]+ba["h"]:
                issues.append(f"Node boxes overlap: {a}, {b}")
    return issues

def edge_path(s: tuple, t: tuple, waypoints=None) -> str:
    x1, y1 = s; x2, y2 = t
    if waypoints:
        pts = [(x1, y1)] + [tuple(p) for p in waypoints] + [(x2,y2)]
        parts = [f"M{x1},{y1}"]
        for a,b in zip(pts, pts[1:]):
            dx = max(18, abs(b[0]-a[0])*.42)
            direction = 1 if b[0] >= a[0] else -1
            parts.append(f"C{a[0]+direction*dx},{a[1]} {b[0]-direction*dx},{b[1]} {b[0]},{b[1]}")
        return " ".join(parts)
    if x2 > x1:
        dx = max(40, (x2-x1)*.46)
        return f"M{x1},{y1} C{x1+dx},{y1} {x2-dx},{y2} {x2},{y2}"
    # Return edge: preserve direction, run outside the node headers.
    y = min(y1,y2)-110
    return f"M{x1},{y1} C{x1+55},{y1} {x1+65},{y} {x1+20},{y} H{x2-30} C{x2-70},{y} {x2-60},{y2} {x2},{y2}"

def avoid_node_boxes(s: tuple, t: tuple, boxes: dict, source_node: str, target_node: str):
    """Route a forward edge above/below all cards if its default cubic hits a third card.

    This is a conservative small-graph router, not an optimal crossing minimizer.
    Explicit waypoints still take precedence and are checked in browser QA.
    """
    x1,y1=s; x2,y2=t
    if x2 <= x1:
        return None
    dx=max(40,(x2-x1)*.46)
    hit=False
    obstacles=[b for nid,b in boxes.items() if nid not in {source_node,target_node}]
    for k in range(101):
        u=k/100; v=1-u
        x=v**3*x1+3*v*v*u*(x1+dx)+3*v*u*u*(x2-dx)+u**3*x2
        y=v**3*y1+3*v*v*u*y1+3*v*u*u*y2+u**3*y2
        if any(b['x']-4<x<b['x']+b['w']+4 and b['y']-4<y<b['y']+b['h']+4 for b in obstacles):
            hit=True;break
    if not hit:
        return None
    top=min(b['y'] for b in boxes.values())-32
    bottom=max(b['y']+b['h'] for b in boxes.values())+30
    channel=top if top>=10 and abs(y1-top)+abs(y2-top)<=abs(y1-bottom)+abs(y2-bottom) else bottom
    return [[x1+25,channel],[x2-25,channel]]

def render_svg(model: dict, report: dict, boxes: dict) -> tuple[str, dict]:
    ns, fs = index_model(model)
    errors = geometry_issues(boxes)
    if errors:
        raise ModelError("\n".join(errors))
    W = max(b["x"]+b["w"] for b in boxes.values())+45
    H = max(b["y"]+b["h"] for b in boxes.values())+48
    H = max(H, 450)
    esc = lambda s: html.escape(str(s), quote=True)
    out = []
    def add(s): out.append(s)
    def text(x,y,s,size=13,color="#233C57",weight=500,anchor="start",cls=""):
        add(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}" class="{cls}">{esc(s)}</text>')
    ports = {}
    for n in model["nodes"]:
        b = boxes[n["id"]]
        for i,f in enumerate(n["fields"]):
            ref = n["id"]+"."+f["id"]
            ports[ref] = {"x1": b["x"], "x2": b["x"]+b["w"], "y": b["y"]+HEADER+i*ROW+24}
    add(f'<svg xmlns="http://www.w3.org/2000/svg" id="lineage-svg" role="img" aria-label="{esc(model["title"])}" viewBox="0 0 {W} {H}" width="{W}" height="{H}">')
    add('<defs><pattern id="dots" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".65" fill="#DCE5EF"/></pattern><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 1 L9 5 L0 9 Z" fill="context-stroke"/></marker></defs>')
    add('<style>text{font-family:Inter,"Noto Sans CJK SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif}.field{cursor:pointer}.field:focus{outline:none}.field.selected .row-bg{stroke:#B67727;stroke-width:2}.dep{fill:none;stroke-linecap:round;stroke-linejoin:round;transition:opacity .15s}.dep.dim{opacity:.09}.dep.on{stroke-width:3;opacity:1}.field.dim{opacity:.68}.flow{fill:none;stroke:#ABBACD;stroke-width:4;opacity:.35}.flow.focused{opacity:.7}.node-frame{filter:drop-shadow(0 3px 6px #29486B08)}.field:hover .row-bg,.field:focus .row-bg{stroke:#7CA7D6;stroke-width:2}</style>')
    add(f'<rect width="{W}" height="{H}" fill="#FAFCFF"/><rect width="{W}" height="{H}" fill="url(#dots)" opacity=".65"/>')
    # Structural edges are derived from the same field graph, not maintained separately.
    structural = set()
    for f in fs.values():
        for d in dependencies(f):
            a, b = fs[d["ref"]]["node"], f["node"]
            if a != b: structural.add((a,b))
    add('<g id="flow-edges" style="display:none">')
    for a,b in sorted(structural):
        aa, bb = boxes[a], boxes[b]
        start,end=(aa["x"]+aa["w"],aa["y"]+34),(bb["x"],bb["y"]+34)
        p = edge_path(start,end,avoid_node_boxes(start,end,boxes,a,b))
        add(f'<path class="flow" data-source="{a}" data-target="{b}" d="{p}" marker-end="url(#arrow)"/>')
    add('</g><g id="dependency-edges">')
    routes = model.get("routes", {})
    for target, f in fs.items():
        t = ports[target]
        for d in dependencies(f):
            source = d["ref"]; s = ports[source]
            role = d["role"]
            color = "#8F68BF" if role == "selector" else "#748396" if role == "condition" else COLORS[f["op"]]
            if fs[source].get("origin", {}).get("kind") == "config" and role == "value": color="#9162C9"
            dash = ' stroke-dasharray="5 4"' if role == "selector" else ' stroke-dasharray="2 5"' if role == "condition" else ""
            start,end=(s["x2"],s["y"]),(t["x1"],t["y"])
            via=routes.get(source+"->"+target)
            if via is None:
                via=avoid_node_boxes(start,end,boxes,fs[source]["node"],f["node"])
            p = edge_path(start,end,via)
            title=f"{source} → {target} · {role}"+(" · "+d["when"] if d.get("when") else "")
            add(f'<path class="dep" data-source="{esc(source)}" data-target="{esc(target)}" data-role="{role}" data-when="{esc(d.get("when",""))}" d="{p}" stroke="{color}" stroke-width="1.65"{dash} marker-end="url(#arrow)"><title>{esc(title)}</title></path>')
    add('</g><g id="control-edges">')
    for e in model.get("controls", []):
        a,b = boxes[e["from"]],boxes[e["to"]]
        p = edge_path((a["x"]+a["w"],a["y"]+24),(b["x"],b["y"]+24),e.get("via"))
        add(f'<path class="control" d="{p}" fill="none" stroke="#63748A" stroke-width="1.5" stroke-dasharray="8 6" marker-end="url(#arrow)"><title>{esc(e["label"])}</title></path>')
        lx=(a["x"]+a["w"]+b["x"])/2; ly=min(a["y"],b["y"])+16
        text(lx,ly,fit(e["label"],180,11),11,"#657B94",550,"middle")
    add('</g>')
    for n in model["nodes"]:
        b = boxes[n["id"]]; x,y,w,h=b["x"],b["y"],b["w"],b["h"]
        bg,stroke,accent = NODE_COLORS[n["kind"]]
        add(f'<g class="node" data-node="{n["id"]}">')
        add(f'<rect class="node-frame" x="{x}" y="{y}" width="{w}" height="{h}" rx="15" fill="white" stroke="{stroke}" stroke-width="1.4"/>')
        add(f'<path d="M{x+15},{y} H{x+w-15} Q{x+w},{y} {x+w},{y+15} V{y+70} H{x} V{y+15} Q{x},{y} {x+15},{y}" fill="{bg}"/>')
        text(x+16,y+29,fit(n["label"],w-30,17),17,"#233C57",750)
        text(x+16,y+52,fit(n.get("subtitle",n["id"]),w-30,10.5),10.5,"#7A8CA3")
        text(x+16,y+85,"输出字段 · 输入依赖接在左端",10,"#8091A6")
        for i, f in enumerate(n["fields"]):
            ref = n["id"]+"."+f["id"]; fy=y+HEADER+i*ROW
            deps=dependencies(f); op=f["op"]; color=COLORS[op]
            origin = f.get("origin", {})
            if origin.get("kind") in {"database","config"}: color="#9162C9"
            if origin:
                from_text = "源：" + origin["locator"]
            elif op == "unknown": from_text="? 来源待确认"
            else:
                from_text="← "+" + ".join(ns[fs[d["ref"]]["node"]].get("short", ns[fs[d["ref"]]["node"]]["label"])+"."+fs[d["ref"]]["label"] for d in deps)
            formula = f.get("display_rule",f.get("rule",from_text))
            full_title=f'{n["label"]} · {f["label"]} ({ref})\n{from_text}\n{f.get("rule", "")}\n{f.get("note", "")}'
            add(f'<g class="field" data-field="{esc(ref)}" role="button" tabindex="0" aria-label="{esc(f["label"]+" "+ref)}"><title>{esc(full_title)}</title>')
            add(f'<rect class="row-bg" x="{x+9}" y="{fy}" width="{w-18}" height="61" rx="7" fill="{bg if op != "unknown" else "#FFF0F2"}" fill-opacity=".53" stroke="#DFE7F0" stroke-width=".8"/>')
            add(f'<rect x="{x+17}" y="{fy+11}" width="3" height="14" rx="1.5" fill="{color}"/>')
            text(x+27,fy+22,fit(f["label"],w-116,13),13,"#203B59",700)
            badge = OP_LABELS[op]
            text(x+w-16,fy+22,badge,10,color,650,"end")
            text(x+27,fy+39,fit(f["id"],w-106,11),11,"#536B86",500)
            text(x+w-16,fy+39,fit(f["type"],66,9.5),9.5,"#8292A6",500,"end")
            text(x+27,fy+54,fit(formula,w-48,9.5),9.5,"#7990A4",450)
            if deps or op == "unknown":
                add(f'<circle cx="{x}" cy="{fy+24}" r="3.8" fill="{color}" stroke="white" stroke-width="1.2"/>')
            add(f'<circle cx="{x+w}" cy="{fy+24}" r="3.8" fill="{color}" stroke="white" stroke-width="1.2"/>')
            add('</g>')
        add('</g>')
    for ann in model.get("annotations", []):
        text(ann["x"],ann["y"],ann["text"],ann.get("size",12),"#7B8DA5",550)
    add('</svg>')
    return "\n".join(out), {"width": W,"height": H,"boxes": boxes,"ports": ports}

def build(model_path: Path, output_dir: Path, strict=False) -> dict:
    model = json.loads(model_path.read_text(encoding="utf-8"))
    report = validate(model)
    if strict and len(report["covered_outputs"]) != len(report["outputs"]):
        raise ModelError("--strict: some output fields have unresolved roots.")
    boxes = layout(model)
    svg, geo = render_svg(model, report, boxes)
    report["geometry"] = geo
    template_path = Path(__file__).resolve().parents[1] / "assets" / "viewer.html"
    template = template_path.read_text(encoding="utf-8")
    def safe_json(o):
        return json.dumps(o,ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = template.replace("__TITLE__", html.escape(model["title"])).replace("__SVG__",svg).replace("__MODEL_JSON__",safe_json(model)).replace("__REPORT_JSON__",safe_json(report))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir/"index.html").write_text(page,encoding="utf-8")
    (output_dir/"diagram.svg").write_text(svg,encoding="utf-8")
    (output_dir/"model.json").write_text(json.dumps(model,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (output_dir/"validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="cmd",required=True)
    for name in ("validate","build","trace"):
        q=sub.add_parser(name); q.add_argument("model",type=Path)
        if name=="build": q.add_argument("--out",required=True,type=Path); q.add_argument("--strict",action="store_true")
        if name=="trace": q.add_argument("field")
    args=p.parse_args()
    try:
        if args.cmd=="build":
            r=build(args.model,args.out,args.strict)
            print(json.dumps({"output":str(args.out.resolve()), "nodes":r["nodes"],"fields":r["fields"],"covered":f'{len(r["covered_outputs"])}/{len(r["outputs"])}',"warnings":r["warnings"]},ensure_ascii=False,indent=2))
        else:
            m=json.loads(args.model.read_text(encoding="utf-8")); r=validate(m)
            if args.cmd=="trace":
                _,fs=index_model(m)
                if args.field not in fs: raise ModelError(f"Unknown field: {args.field}")
                r=trace(fs,args.field)
            print(json.dumps(r,ensure_ascii=False,indent=2))
        return 0
    except (ModelError,OSError,json.JSONDecodeError) as e:
        print(f"Error: {e}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
