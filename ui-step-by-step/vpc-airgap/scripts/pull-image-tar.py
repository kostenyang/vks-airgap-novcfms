"""Staging 機(有網路、沒有 docker)用:把 registry 上的 image 存成 `docker load` 吃得下的 tar
用法:python pull-image-tar.py <image[:tag]> <out.tar>     例:nginxinc/nginx-unprivileged:1.29-alpine
只抓 linux/amd64。layer 解壓成 tar(diff_id 對得上 config)。
"""
import gzip, hashlib, io, json, sys, tarfile, urllib.request

def parse(ref):
    name, _, tag = ref.partition(":")
    tag = tag or "latest"
    if "/" not in name:
        name = "library/" + name
    return name, tag

def get(url, token=None, accept=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if accept:
        req.add_header("Accept", accept)
    return urllib.request.urlopen(req, timeout=300)

def main(ref, out):
    repo, tag = parse(ref)
    tok = json.load(get(f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"))["token"]
    reg = f"https://registry-1.docker.io/v2/{repo}"
    acc = ",".join([
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json"])
    m = json.load(get(f"{reg}/manifests/{tag}", tok, acc))
    if "manifests" in m:  # index → linux/amd64
        d = next(x for x in m["manifests"] if x.get("platform", {}).get("os") == "linux" and x["platform"].get("architecture") == "amd64")
        m = json.load(get(f"{reg}/manifests/{d['digest']}", tok, acc))
    cfg_digest = m["config"]["digest"]
    cfg = get(f"{reg}/blobs/{cfg_digest}", tok).read()
    assert "sha256:" + hashlib.sha256(cfg).hexdigest() == cfg_digest
    diff_ids = json.loads(cfg)["rootfs"]["diff_ids"]
    with tarfile.open(out, "w") as tf:
        def add(name, data):
            ti = tarfile.TarInfo(name); ti.size = len(data); tf.addfile(ti, io.BytesIO(data))
        cfg_name = cfg_digest.split(":")[1] + ".json"
        add(cfg_name, cfg)
        layers = []
        for i, l in enumerate(m["layers"]):
            blob = get(f"{reg}/blobs/{l['digest']}", tok).read()
            assert "sha256:" + hashlib.sha256(blob).hexdigest() == l["digest"], "blob digest mismatch"
            raw = gzip.decompress(blob) if blob[:2] == b"\x1f\x8b" else blob
            assert "sha256:" + hashlib.sha256(raw).hexdigest() == diff_ids[i], "diff_id mismatch"
            p = f"{diff_ids[i].split(':')[1]}/layer.tar"
            add(p, raw); layers.append(p)
            print(f"  layer {i + 1}/{len(m['layers'])} {len(blob) / 2**20:.1f} MB")
        short = repo[len("library/"):] if repo.startswith("library/") else repo
        add("manifest.json", json.dumps([{"Config": cfg_name, "RepoTags": [f"{short}:{tag}"], "Layers": layers}]).encode())
    print(f"saved {short}:{tag} -> {out}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
