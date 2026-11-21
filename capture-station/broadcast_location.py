"""County-only location in the lower-left broadcast safe area."""
import os,sys,time
from pathlib import Path
from PIL import ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'uap-lab'))
from station_location import display_label
from air_traffic import public_region

class LocationOverlay:
    def __init__(self,root=None):
        self.root=Path(root) if root else Path(os.environ.get('UAP_LAB_DATA','/Volumes/UFO-Field/uap-lab')).parent
        font=Path(__file__).resolve().parents[1]/'uap-lab/static/fonts/IBMPlexMono-Regular.woff2'
        self.font=ImageFont.truetype(str(font),14)
        self.label='';self.checked=-float('inf')
    def draw(self,canvas,frame=None,standby=False,ink=None):
        now=time.monotonic()
        if now-self.checked>=10:
            self.label=display_label(public_region(self.root));self.checked=now
        if not self.label:return
        draw=ImageDraw.Draw(canvas)
        x=30;y=canvas.height-26
        ink=ink or ((155,201,140,255) if standby else (255,255,255,255))
        draw.text((x,y),self.label,font=self.font,anchor='lb',fill=ink)
