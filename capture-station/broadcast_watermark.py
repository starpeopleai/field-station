"""Composite the stacked StarPeople.ai Network watermark."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

class Watermark:
    def __init__(self):
        from broadcast_location import LocationOverlay
        self.location=LocationOverlay()
        assets=Path(__file__).with_name('assets')
        self.mask=Image.open(assets/'starpeople-mark-mono.png').convert('RGBA').getchannel('A').resize((28,28),Image.Resampling.LANCZOS)
        self.font=ImageFont.truetype(str(assets/'AtkinsonHyperlegible-Regular.ttf'),18)

    def draw(self,canvas,frame=None,standby=False,location_ink=None):
        self.location.draw(canvas,frame,standby,ink=location_ink)
        bright=False
        if frame is not None and not standby:
            crop=frame.resize((1280,720)).convert('L').crop((30,26,285,74)).resize((16,4))
            bright=sum(crop.getdata())/(16*4)>155
        ink=(155,201,140) if standby else (17,17,17) if bright else (255,255,255)
        logo=Image.new('RGBA',self.mask.size,(*ink,0))
        logo.putalpha(self.mask.point(lambda a:round(a*.88)))
        canvas.alpha_composite(logo,(36,35))
        draw=ImageDraw.Draw(canvas)
        lines=('starpeople.ai','network')
        heights=[self.font.getbbox(line,anchor='lt')[3] for line in lines]
        y=49-(sum(heights)+2)/2
        for line,height in zip(lines,heights):
            draw.text((72,round(y)),line,font=self.font,anchor='lt',fill=(*ink,225))
            y+=height+2
