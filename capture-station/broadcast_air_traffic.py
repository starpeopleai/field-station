"""Public aircraft radar: licensed reports only, no landmark or center labels."""
import json,math,time
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

FONT=Path(__file__).resolve().parents[1]/'uap-lab/static/fonts/IBMPlexMono-Regular.woff2'
class AircraftOverlay:
 def __init__(self,root):
  self.root=Path(root)/'air-traffic';self.checked=-float('inf');self.data={};self.config={}
  self.font=ImageFont.truetype(str(FONT),22);self.small=ImageFont.truetype(str(FONT),18)
 def read(self):
  if time.monotonic()-self.checked<2:return
  self.checked=time.monotonic()
  try:self.data=json.loads((self.root/'public-latest.json').read_text());self.config=json.loads((self.root/'settings.json').read_text())
  except (OSError,ValueError):self.data={};self.config={}
 def reports(self,now):
  d=self.data;c=self.config;center=d.get('center',{});radius=d.get('radius_nm',0)
  age=now-d.get('sampled_epoch',0)
  valid=(d.get('provider')=='adsb.lol' and d.get('license')=='ODbL-1.0' and 0<=age<=210 and radius>0 and all(center.get(k)==c.get(k) for k in ('latitude','longitude')) and radius==c.get('radius_nm'))
  return (d.get('aircraft',[]) if valid else []),age,valid
 def render(self,ink,now=None):
  now=time.time() if now is None else now;reports,age,valid=self.reports(now)
  canvas=Image.new('RGBA',(460,490));draw=ImageDraw.Draw(canvas);cx,cy,r=230,252,182
  draw.text((0,0),'Air traffic',font=self.font,fill=ink)
  draw.text((460,2),f'{int(age)}s ago' if valid else 'Data unavailable',font=self.small,fill=ink,anchor='rt')
  azimuth=self.config.get('camera_azimuth_deg')
  oriented=isinstance(azimuth,(int,float)) and not isinstance(azimuth,bool) and math.isfinite(azimuth) and 0<=azimuth<360
  heading=math.radians(azimuth) if oriented else 0
  faint=(*ink[:3],90)
  for fraction in (1/3,2/3,1):
   rr=r*fraction;draw.ellipse((cx-rr,cy-rr,cx+rr,cy+rr),outline=faint,width=2)
  draw.line((cx-r,cy,cx+r,cy),fill=faint,width=1);draw.line((cx,cy-r,cx,cy+r),fill=faint,width=1)
  for label,degrees in [('N',0),('E',90),('S',180),('W',270)]:
   angle=math.radians(degrees)-heading;draw.text((cx+math.sin(angle)*210,cy-math.cos(angle)*210),label,font=self.small,fill=ink,anchor='mm')
  draw.ellipse((cx-3,cy-3,cx+3,cy+3),fill=ink)
  if oriented:
   angle=0
   for start in range(0,r,15):
    end=min(start+8,r);draw.line((cx+math.sin(angle)*start,cy-math.cos(angle)*start,cx+math.sin(angle)*end,cy-math.cos(angle)*end),fill=ink,width=2)
   draw.text((0,28),f'Camera {azimuth:g}°',font=self.small,fill=ink)
  radius=self.config.get('radius_nm',15/1.150779448);center=self.config
  for a in reports:
   try:
    p1,p2=math.radians(center['latitude']),math.radians(a['latitude']);dl=math.radians(a['longitude']-center['longitude']);dp=p2-p1
    h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    distance=3440.065*2*math.asin(math.sqrt(max(0,min(1,h))))
    if distance>radius:continue
    bearing=math.atan2(math.sin(dl)*math.cos(p2),math.cos(p1)*math.sin(p2)-math.sin(p1)*math.cos(p2)*math.cos(dl))
    x=cx+math.sin(bearing-heading)*distance/radius*r;y=cy-math.cos(bearing-heading)*distance/radius*r
    track=a.get('track_deg')
    if isinstance(track,(int,float)) and math.isfinite(track):
     theta=math.radians(track)-heading;points=[(x+px*math.cos(theta)-py*math.sin(theta),y+px*math.sin(theta)+py*math.cos(theta)) for px,py in [(0,-9),(6,6),(0,3),(-6,6)]];draw.polygon(points,fill=ink)
    else:draw.ellipse((x-3,y-3,x+3,y+3),fill=ink)
   except (KeyError,TypeError,ValueError):continue
  draw.text((0,488),'ADSB.lol · ODbL',font=self.small,fill=ink,anchor='lb');draw.text((460,488),f'{round(radius*1.150779448)} mi radius',font=self.small,fill=ink,anchor='rb')
  return canvas.resize((230,245),Image.Resampling.LANCZOS)
 def draw(self,canvas,ink):
  self.read();canvas.alpha_composite(self.render(ink),(30,canvas.height-305))
