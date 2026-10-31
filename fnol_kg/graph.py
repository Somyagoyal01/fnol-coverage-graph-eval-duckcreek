"""Policy knowledge graph: policies, vehicles, drivers, coverages and exclusions as nodes and typed edges."""
import networkx as nx


def build_graph(policies):
    g = nx.MultiDiGraph()
    for p in policies:
        pid = p["policy_id"]
        g.add_node(pid, kind="Policy", holder=p["holder"], effective=p["effective"],
                   expiry=p["expiry"], cancelled_on=p["cancelled_on"])
        for v in p["vehicles"]:
            g.add_node(v["vehicle_id"], kind="Vehicle", make=v["make"], model=v["model"], year=v["year"])
            g.add_edge(pid, v["vehicle_id"], rel="COVERS_VEHICLE")
        for d in p["drivers"]:
            dn = f"D:{d['name'].lower()}"
            g.add_node(dn, kind="Driver", name=d["name"])
            g.add_edge(pid, dn, rel="EXCLUDES_DRIVER" if d["excluded"] else "LISTS_DRIVER")
        for c in p["coverages"]:
            cn = f"{pid}:COV:{c['type']}"
            g.add_node(cn, kind="Coverage", type=c["type"], limit=c["limit"], deductible=c["deductible"])
            g.add_edge(pid, cn, rel="HAS_COVERAGE")
        for e in p["exclusions"]:
            en = f"EXCL:{e}"
            g.add_node(en, kind="Exclusion", name=e)
            g.add_edge(pid, en, rel="HAS_EXCLUSION")
    return g


def neighbours(g, pid, rel):
    """Targets of edges with relation `rel` leaving policy `pid`."""
    return [t for _, t, d in g.out_edges(pid, data=True) if d["rel"] == rel]


def triple_exists(g, s, rel, o):
    return g.has_node(s) and any(t == o and d["rel"] == rel for _, t, d in g.out_edges(s, data=True))


def stats(g):
    kinds = {}
    for _, d in g.nodes(data=True):
        kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
    return {"nodes": g.number_of_nodes(), "edges": g.number_of_edges(), **kinds}
