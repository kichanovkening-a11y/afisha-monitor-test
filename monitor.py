import requests,bs4,re,json,datetime,time,hashlib
from pathlib import Path
from urllib.parse import urljoin,quote
ROOT="https://vip-teatre.ru/repertuar/"
MONTHS={"января":1,"февраля":2,"марта":3,"апреля":4,"мая":5,"июня":6,"июля":7,"августа":8,"сентября":9,"октября":10,"ноября":11,"декабря":12}
SELLERS={"Кассир.ру":"https://www.kassir.ru/search?query=","Яндекс Афиша":"https://afisha.yandex.ru/moscow/search?query=","Афиша.ру":"https://www.afisha.ru/search/?q=","Тикетленд":"https://www.ticketland.ru/search/?q="}
session=requests.Session()
session.headers.update({"User-Agent":"Mozilla/5.0 (compatible; AfishaMonitorTest/1.0)","Accept-Language":"ru-RU,ru;q=0.9"})
def fetch(url):
 try:
  r=session.get(url,timeout=20);r.raise_for_status();return r
 except requests.RequestException as e:
  print("FETCH ERROR",url,type(e).__name__,str(e)[:300],flush=True)
  return None
def norm(s):return re.sub(r"\s+"," ",s or "").strip()
def dates(text):
 result=[]
 pattern=r"(?<!\d)(\d{1,2})\s+("+"|".join(MONTHS)+r")\s+(20\d{2})"
 for m in re.finditer(pattern,text,re.I):
  try:d=datetime.date(int(m[3]),MONTHS[m[2].lower()],int(m[1]))
  except ValueError:continue
  if d<datetime.date.today():continue
  tail=text[m.end():m.end()+110]
  tm=re.search(r"(?:сеанс\s*)?(\d{1,2}):(\d{2})",tail,re.I)
  item={"date":d.isoformat(),"time":f"{int(tm[1]):02d}:{tm[2]}" if tm else ""}
  if item not in result:result.append(item)
 return result
def page(url,name):
 r=fetch(url)
 if not r:return {"title":name,"url":url,"error":"Страница недоступна","dates":[]}
 soup=bs4.BeautifulSoup(r.text,"html.parser")
 title=norm(soup.h1.get_text(" ",strip=True)) if soup.h1 else name
 for el in soup.select("script,style,nav,footer,header"):el.decompose()
 body=soup.select_one("main") or soup.select_one("article") or soup.body or soup
 text=norm(body.get_text(" ",strip=True))
 venue=""
 match=re.search(r"Даты\s+и\s+место\s*:?\s*(.{0,160})",text,re.I)
 if match:venue=norm(re.split(r"\d{1,2}\s+(?:"+"|".join(MONTHS)+")",match[1],maxsplit=1,flags=re.I)[0])[:120]
 img=body.select_one("img[src]")
 poster=urljoin(url,img.get("src","")) if img else ""
 paragraphs=[norm(p.get_text(" ",strip=True)) for p in body.select("p")]
 desc=next((x[:500] for x in paragraphs if len(x)>80),"")
 cast=list(dict.fromkeys(norm(a.get_text(" ",strip=True)) for a in body.select('a[href*="/aktery/"]') if norm(a.get_text(" ",strip=True))))
 duration=re.search(r"(?:продолжительность|длительность)\s*:?\s*([^.;]{3,60})",text,re.I)
 return {"title":title,"url":url,"venue":venue,"poster":poster,"description":desc,"cast":cast,"duration":norm(duration[1]) if duration else "","dates":dates(text)}
def probe(show,name,base):
 url=base+quote(show["title"]+" "+show["date"])
 r=fetch(url)
 if not r:return {"status":"unverified","reason":"Поиск недоступен или заблокирован","search_url":url}
 soup=bs4.BeautifulSoup(r.text,"html.parser")
 for el in soup.select("script,style,nav,header,footer"):el.decompose()
 txt=norm(soup.get_text(" ",strip=True)).lower()
 tokens=re.findall(r"[а-яёa-z]{4,}",show["title"].lower())
 if not tokens or sum(t in txt for t in tokens)<max(1,len(tokens)-1):
  return {"status":"unverified","reason":"Совпадение не подтверждено","search_url":url}
 return {"status":"candidate","reason":"Название найдено в поиске; дата и площадка не подтверждены","search_url":url}
def main():
 r=fetch(ROOT)
 if not r:raise RuntimeError("Репертуар недоступен; прежние результаты сохранены")
 soup=bs4.BeautifulSoup(r.text,"html.parser")
 links={}
 for a in soup.select("a[href]"):
  u=urljoin(ROOT,a.get("href","")).replace("/repertuar/repertuar/","/repertuar/")
  if re.search(r"^https://(?:www\.)?vip-teatre\.ru/repertuar/[^/?#]+\.html$",u) and not re.search("arhiv|archive",u,re.I):
   links[u]=norm(a.get_text(" ",strip=True))
 if not links:raise RuntimeError("Не найдены страницы спектаклей; данные не перезаписаны")
 shows=[];errors=[]
 for u,name in links.items():
  p=page(u,name)
  if "error" in p:errors.append(u)
  events=p.pop("dates",[])
  if not events:shows.append({**p,"id":hashlib.sha1(u.encode()).hexdigest()[:12],"date":"","time":"","status":"undated","sellers":{}})
  for e in events:
   s={**p,**e,"id":hashlib.sha1((u+e["date"]+e["time"]).encode()).hexdigest()[:12],"status":"dated"}
   s["sellers"]={}
   for seller,base in SELLERS.items():
    s["sellers"][seller]=probe(s,seller,base);time.sleep(.3)
   shows.append(s)
  time.sleep(.4)
 folder=Path("data");folder.mkdir(exist_ok=True)
 now=datetime.datetime.now(datetime.timezone.utc).isoformat()
 (folder/"latest.json").write_text(json.dumps({"updated_at":now,"source":ROOT,"shows":shows,"errors":errors,"count_pages":len(links),"version":2},ensure_ascii=False,indent=2),encoding="utf-8")
 hist=folder/"history.json"
 try:history=json.loads(hist.read_text(encoding="utf-8"))
 except Exception:history=[]
 history.insert(0,{"at":now,"shows":len(shows),"pages":len(links),"errors":len(errors)})
 hist.write_text(json.dumps(history[:90],ensure_ascii=False,indent=2),encoding="utf-8")
 print("Parsed",len(links),"pages;",len(shows),"shows;",len(errors),"errors")
if __name__=="__main__":main()
