"""Get the official square product artwork by exact Nintendo application ID.
No fallback to unrelated art; NUP lacks control icon (verified original build).
Adapted in approach from NX Play StorePage, v1.8.10.
"""
import hashlib, json, plistlib, re, subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, quote, unquote
from urllib.request import Request, urlopen

TITLE="0400486024DEC000"
PAGE="https://www.nintendo.com/us/store/products/the-legend-of-zelda-ocarina-of-time-switch-2/"
HOSTS={"assets.nintendo.com","atum-img-lp1.cdn.nintendo.net"}

class NextData(HTMLParser):
    def __init__(self):
        super().__init__(); self.active=False; self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag=="script" and dict(attrs).get("id")=="__NEXT_DATA__": self.active=True
    def handle_endtag(self,tag):
        if tag=="script": self.active=False
    def handle_data(self,data):
        if self.active:self.parts.append(data)

def square_url(html):
    parser=NextData();parser.feed(html)
    state=json.loads("".join(parser.parts))["props"]["pageProps"]["initialApolloState"]
    products=[x for x in state.values() if isinstance(x,dict) and x.get("__typename")=="Product" and str(x.get("applicationId","")).upper()==TITLE]
    for p in sorted(products,key=lambda x:(x.get("productImage") is None,str(x.get("sku","")))):
        image=p.get('productImage({"shape":"square"})')
        if not isinstance(image,dict):continue
        if "__ref" in image:image=state.get(image["__ref"],{})
        value=image.get("url") or image.get("publicId")
        if not value:continue
        u=urlsplit(value)
        if u.netloc:
            if u.scheme!="https" or u.hostname not in HOSTS:continue
            if u.hostname=="atum-img-lp1.cdn.nintendo.net":return value
            if "/image/fetch/" in value:
                inner=unquote(value.split("/image/fetch/",1)[1]); at=inner.find("https://")
                if at>=0 and urlsplit(inner[at:]).hostname=="atum-img-lp1.cdn.nintendo.net":return inner[at:]
                continue
            if "/image/upload/" not in u.path:continue
            path=u.path.split("/image/upload/",1)[1]
        else:path=value
        parts=path.split("/")
        while parts and "_" in parts[0]:parts.pop(0)
        if parts and parts[0]=="store":return "https://assets.nintendo.com/image/upload/f_jpg/q_auto/"+quote(unquote("/".join(parts)),safe="/-_.")
    raise RuntimeError("Nintendo did not provide square artwork for exact title ID "+TITLE)

def fetch(url,hosts,limit):
    with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"*/*"}),timeout=60) as r:
        u=urlsplit(r.geturl())
        if u.scheme!="https" or u.hostname not in hosts:raise RuntimeError("unexpected Nintendo redirect")
        data=r.read(limit+1)
        if not data or len(data)>limit:raise RuntimeError("invalid Nintendo response size")
        return data

def prepare(path):
    html=fetch(PAGE,{"www.nintendo.com"},30*1024*1024).decode("utf-8")
    url=square_url(html)
    path.write_bytes(fetch(url,HOSTS,12*1024*1024))
    # Check that the selected product image really is a square, decoded by macOS.
    info=subprocess.check_output(["sips","-g","pixelWidth","-g","pixelHeight",str(path)],text=True)
    dims=[int(x) for x in re.findall(r"pixel(?:Width|Height):\s*(\d+)",info)]
    if len(dims)!=2 or dims[0]!=dims[1] or dims[0]<256:raise RuntimeError("official icon is not a usable square")
    return {"source_page":PAGE,"image_url":url,"title_id":TITLE,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"pixels":dims[0]}

def install(app,source):
    # Legacy PNG entries are supported by iOS and by sideloaders. Keep the
    # source Assets.car intact; remove the stale icon-name reference only.
    files={"GameIcon60@2x.png":120,"GameIcon60@3x.png":180,
           "GameIcon76@2x~ipad.png":152,"GameIcon83.5@2x~ipad.png":167}
    for name,n in files.items():
        dest=app/name
        subprocess.run(["sips","-s","format","png","-z",str(n),str(n),str(source),"--out",str(dest)],check=True)
        if dest.stat().st_size<1000:raise RuntimeError("invalid generated icon "+name)
    pl=app/"Info.plist"; data=plistlib.loads(pl.read_bytes())
    data.pop("CFBundleIconName",None);data.pop("CFBundleIconFile",None)
    data["CFBundleIconFiles"]=["GameIcon60"]
    for key,names in (("CFBundleIcons",["GameIcon60"]),("CFBundleIcons~ipad",["GameIcon60","GameIcon76","GameIcon83.5"])):
        group=data.get(key,{})
        group["CFBundlePrimaryIcon"]={"CFBundleIconFiles":names,"UIPrerenderedIcon":False}
        data[key]=group
    pl.write_bytes(plistlib.dumps(data))
    return {name:hashlib.sha256((app/name).read_bytes()).hexdigest() for name in files}
