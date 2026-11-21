"""Public aircraft radar: licensed reports only, no landmark or center labels."""
import json,math,time,hashlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"shared"))
from camera_optics import field_of_view, aircraft_view
from PIL import Image,ImageDraw,ImageFont

FONT=Path(__file__).resolve().parents[1]/'uap-lab/static/fonts/IBMPlexMono-Regular.woff2'
class AircraftOverlay:
 def __init__(self,root):
  self.root=Path(root)/'air-traffic';self.checked=-float('inf');self.data={};self.config={};self.station_altitude_ft=None;self.terrain_source=None
  self.font=ImageFont.truetype(str(FONT),22);self.small=ImageFont.truetype(str(FONT),18)
 def read(self):
  if time.monotonic()-self.checked<2:return
  self.checked=time.monotonic()
  try:self.data=json.loads((self.root/'public-latest.json').read_text());self.config=json.loads((self.root/'settings.json').read_text())
  except (OSError,ValueError):self.data={};self.config={};self.station_altitude_ft=None;self.terrain_source=None
  self.station_altitude_ft=None;self.terrain_source=None
  ground=self.config.get('station_altitude_ft')
  if not isinstance(ground,(int,float)):
   try:
    terrain=json.loads((self.root/'terrain-elevation.json').read_text())
    key=hashlib.sha256(json.dumps([self.config['latitude'],self.config['longitude']]).encode()).hexdigest()[:16]
    ground=terrain.get('ground_altitude_ft') if terrain.get('center_key')==key else None
    if ground is not None:self.terrain_source=terrain.get('source')
   except (OSError,ValueError,KeyError):ground=None
  if isinstance(ground,(int,float)) and math.isfinite(ground):self.station_altitude_ft=ground+self.config.get('camera_height_ft',0)
 def reports(self,now):
  d=self.data;c=self.config;center=d.get('center',{});radius=d.get('radius_nm',0)
  age=now-d.get('sampled_epoch',0)
  valid=(d.get('provider')=='adsb.lol' and d.get('license')=='ODbL-1.0' and 0<=age<=210 and radius>0 and all(center.get(k)==c.get(k) for k in ('latitude','longitude')) and radius==c.get('radius_nm'))
  return (d.get('aircraft',[]) if valid else []),age,valid
 def render(self,ink,now=None):
  now=time.time() if now is None else now;reports,age,valid=self.reports(now)
  canvas=Image.new('RGBA',(460,1120));draw=ImageDraw.Draw(canvas);cx,cy,r=230,318,214
  draw.text((0,0),'Air traffic',font=self.font,fill=ink,anchor='lt')
  azimuth=self.config.get('camera_azimuth_deg')
  oriented=isinstance(azimuth,(int,float)) and not isinstance(azimuth,bool) and math.isfinite(azimuth) and 0<=azimuth<360
  heading=math.radians(azimuth) if oriented else 0
  fov=field_of_view(self.config)
  if oriented:
   half=fov['azimuth_span_deg']/2
   draw.pieslice((cx-r,cy-r,cx+r,cy+r),-90-half,-90+half,fill=(*ink[:3],30),outline=(*ink[:3],140),width=1)
  faint=(*ink[:3],90)
  for fraction in (1/3,2/3,1):
   rr=r*fraction;draw.ellipse((cx-rr,cy-rr,cx+rr,cy+rr),outline=faint,width=2)
  draw.line((cx-r,cy,cx+r,cy),fill=faint,width=1);draw.line((cx,cy-r,cx,cy+r),fill=faint,width=1)
  for label,degrees in [('N',0),('E',90),('S',180),('W',270)]:
   angle=math.radians(degrees)-heading;draw.text((cx+math.sin(angle)*193,cy-math.cos(angle)*193),label,font=self.small,fill=ink,anchor='mm')
  draw.ellipse((cx-3,cy-3,cx+3,cy+3),fill=ink)
  if oriented:
   angle=0
   for start in range(0,r,15):
    end=min(start+8,r);draw.line((cx+math.sin(angle)*start,cy-math.cos(angle)*start,cx+math.sin(angle)*end,cy-math.cos(angle)*end),fill=ink,width=2)
   draw.text((0,28),f"Camera {azimuth:g}° · {fov['focal_length_mm']:g} mm",font=self.small,fill=ink,anchor='lt')
  radius=self.config.get('radius_nm',15/1.150779448);center=self.config
  total=0;in_view=0;unknown=0;side_rows=[]
  for a in reports:
   try:
    p1,p2=math.radians(center['latitude']),math.radians(a['latitude']);dl=math.radians(a['longitude']-center['longitude']);dp=p2-p1
    h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    distance=3440.065*2*math.asin(math.sqrt(max(0,min(1,h))))
    if distance>radius:continue
    bearing=math.atan2(math.sin(dl)*math.cos(p2),math.cos(p1)*math.sin(p2)-math.sin(p1)*math.cos(p2)*math.cos(dl))
    if not all(math.isfinite(v) for v in (distance,bearing)):continue
    total+=1
    delta=math.atan2(math.sin(bearing-heading),math.cos(bearing-heading))
    view=aircraft_view(self.config,a,self.station_altitude_ft)
    if view:
     if view['in_fov']:in_view+=1
     if view['in_bearing'] and view['in_fov'] is None:unknown+=1
     if view['in_bearing'] and view['relative_height_ft'] is not None:side_rows.append(view)
    x=cx+math.sin(bearing-heading)*distance/radius*r;y=cy-math.cos(bearing-heading)*distance/radius*r
    track=a.get('track_deg')
    if isinstance(track,(int,float)) and math.isfinite(track):
     theta=math.radians(track)-heading;points=[(x+px*math.cos(theta)-py*math.sin(theta),y+px*math.sin(theta)+py*math.cos(theta)) for px,py in [(0,-9),(6,6),(0,3),(-6,6)]];draw.polygon(points,fill=ink)
    else:draw.ellipse((x-3,y-3,x+3,y+3),fill=ink)
    if view and view['in_fov']:draw.rectangle((x-12,y-12,x+12,y+12),outline=ink,width=2)
   except (KeyError,TypeError,ValueError):continue
  draw.text((460,0),f'{total} aircraft' if valid else 'Data unavailable',font=self.small,fill=ink,anchor='rt')
  if valid and oriented:
   label=f'{in_view} in Field of View'+(f' · {unknown} unknown' if unknown else '') if self.station_altitude_ft is not None and fov['elevation_deg'] is not None else 'FoV unavailable'
   draw.text((460,28),label,font=self.small,fill=ink,anchor='rt')
  draw.text((0,554),'Side view',font=self.font,fill=ink,anchor='lt')
  pitch=fov['elevation_deg']
  detail=f'{pitch:g}° ↑ · {fov["vertical_deg"]:.1f}° FoV' if pitch is not None else 'Set camera elevation'
  draw.text((0,582),detail,font=self.small,fill=ink,anchor='lt')
  side=Image.new('RGBA',(460,540));sd=ImageDraw.Draw(side);x0,y0,w,top=0,502,459,74;scale=w/radius;y_scale=(y0-top)/40000;aspect=y_scale*6076.11549/scale
  # Cone is drawn on a clipped layer so steep elevation never covers headings.
  cone=Image.new('RGBA',(w,y0-top));cd=ImageDraw.Draw(cone)
  if pitch is not None:
   angles=[math.radians(pitch-fov['vertical_deg']/2),math.radians(pitch+fov['vertical_deg']/2)]
   verts=[(0,y0-top)]+[(math.cos(v)*5000,y0-top-math.sin(v)*5000*aspect) for v in angles]
   cd.polygon(verts,fill=(*ink[:3],30));cd.line(verts+[verts[0]],fill=(*ink[:3],140),width=1)
   a=math.radians(pitch);cd.line((0,y0-top,math.cos(a)*5000,y0-top-math.sin(a)*5000*aspect),fill=(*ink[:3],140),width=1)
  side.alpha_composite(cone,(x0,top));sd=ImageDraw.Draw(side)
  for frac in (.5,1):
   y=y0-(y0-top)*frac;sd.line((x0,y,x0+w,y),fill=ink,width=1);sd.text((x0+4,y-4),f'{round((y0-y)/y_scale/1000)}k ft',font=self.small,fill=ink,anchor='lb')
  sd.line((x0,top,x0,y0,x0+w,y0),fill=ink,width=1)
  sd.text((x0,y0-8),'0',font=self.small,fill=ink,anchor='lb');sd.text((x0+w,y0-8),f'{round(radius*1.150779448)} mi',font=self.small,fill=ink,anchor='rb')
  for v in side_rows:
   x=x0+v['distance_nm']*scale;y=y0-v['relative_height_ft']*y_scale
   if not top<=y<=y0 or not x0<=x<=x0+w:continue
   sd.ellipse((x-3,y-3,x+3,y+3),fill=ink)
   if v['in_fov']:sd.rectangle((x-8,y-8,x+8,y+8),outline=ink,width=2)
  sd.ellipse((x0-3,y0-3,x0+3,y0+3),fill=ink)
  note='Awaiting fresh aircraft data' if not valid else 'Station elevation unavailable' if self.station_altitude_ft is None else None
  if note:sd.text((220,100),note,font=self.small,fill=ink,anchor='mm')
  draw.text((0,1090),'ADSB.lol · ODbL',font=self.small,fill=ink,anchor='lb');draw.text((230,96),f'{round(radius*1.150779448)} mi radius',font=self.small,fill=ink,anchor='mb')
  if self.terrain_source=='Copernicus / Open-Meteo':draw.text((0,1114),'Terrain: Copernicus / Open-Meteo',font=self.small,fill=ink,anchor='lb')
  row=Image.new('RGBA',(976,566))
  row.alpha_composite(canvas.crop((0,0,460,546)),(0,0))
  row.alpha_composite(canvas.crop((0,554,460,610)),(516,0))
  row.alpha_composite(side.crop((0,0,460,510)),(516,30))
  row.alpha_composite(canvas.crop((0,1072,460,1094)),(0,544))
  row.alpha_composite(canvas.crop((0,1096,460,1120)),(516,542))
  return row.resize((488,283),Image.Resampling.LANCZOS)
 def draw(self,canvas,ink):
  self.read();canvas.alpha_composite(self.render(ink),(canvas.width-518,canvas.height-309))
