"""County-only location in the lower-left broadcast safe area."""
import math,os,re,sys,time
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'uap-lab'))
from station_location import display_label
from air_traffic import public_region, settings, number
from station_weather import live

# Tile order follows the station header weather symbols.
CONDITIONS = ('thunder','snow|ice|freezing|sleet','rain|drizzle|shower','fog|mist|haze|smoke',
              'partly|few clouds|mostly sunny','cloud|overcast','clear|fair|sun')

class LocationOverlay:
    def __init__(self,root=None):
        self.root=Path(root) if root else Path(os.environ.get('UAP_LAB_DATA','/Volumes/UFO-Field/uap-lab')).parent
        font=Path(__file__).resolve().parents[1]/'uap-lab/static/fonts/IBMPlexMono-Regular.woff2'
        self.font=ImageFont.truetype(str(font),14)
        with Image.open(Path(__file__).with_name('assets')/'weather-symbols.png') as sheet:
            self.icons=[sheet.crop((x,0,x+22,22)).getchannel('A') for x in range(0,sheet.width,22)]
        self.weather_text=''
        self.label='';self.checked=-float('inf')
    def draw(self,canvas,frame=None,standby=False,ink=None):
        now=time.monotonic()
        if now-self.checked>=10:
            self.label=display_label(public_region(self.root))
            sample=live(self.root,settings(self.root),time.time())
            self.weather_text=''
            if sample:
                condition=sample.get('conditions') or ''
                self.icon_index=next((i for i,pattern in enumerate(CONDITIONS)
                                      if re.search(pattern,condition,re.I)),len(CONDITIONS))
                fields=(('temperature_2m','°F'),('relative_humidity_2m','% RH'),('pressure_hpa',' hPa'))
                self.weather_text=' · '.join(str(math.floor(sample[k]+0.5))+unit if number(sample.get(k)) else '—'
                                             for k,unit in fields)
            self.checked=now
        if not (self.label or self.weather_text):return
        draw=ImageDraw.Draw(canvas)
        x=30;y=canvas.height-26
        ink=ink or ((155,201,140,255) if standby else (255,255,255,255))
        if self.label:
            draw.text((x,y),self.label,font=self.font,anchor='lb',fill=ink)
        if self.weather_text:
            bottom=y-25 if self.label else y
            bounds=draw.textbbox((x+26,bottom),self.weather_text,font=self.font,anchor='lb')
            top=round((bounds[1]+bounds[3]-22)/2)
            draw.bitmap((x,top),self.icons[self.icon_index],fill=ink)
            draw.text((x+26,bottom),self.weather_text,font=self.font,anchor='lb',fill=ink)
