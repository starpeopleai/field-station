"""Estimated R100 full-width 16:9 field of view and its plan-view bearing envelope.

Canon R100 sensor width: 22.3 mm. Assumes landscape, level roll, no extra
movie crop or digital stabilization crop. A map wedge is not an aircraft match.
"""
import math

def field_of_view(config):
    focal=config.get('camera_focal_length_mm',100)
    if isinstance(focal,bool) or not isinstance(focal,(int,float)) or not math.isfinite(focal) or not 100<=focal<=400:focal=100
    elevation=config.get('camera_elevation_deg')
    if isinstance(elevation,bool) or not isinstance(elevation,(int,float)) or not math.isfinite(elevation) or not -90<=elevation<=90:elevation=None
    horizontal=22.3/(2*focal);vertical=horizontal*9/16
    pitch=math.radians(elevation or 0)
    forward=math.cos(pitch)-abs(math.sin(pitch))*vertical
    span=360 if forward<=0 else math.degrees(2*math.atan2(horizontal,forward))
    return dict(focal_length_mm=focal,horizontal_deg=math.degrees(2*math.atan(horizontal)),
                vertical_deg=math.degrees(2*math.atan(vertical)),azimuth_span_deg=span,
                elevation_deg=elevation,estimated=True)


def aircraft_view(config, aircraft, station_altitude_ft=None):
    """Approximate sightline/frustum, using reported pressure altitude and terrain MSL.

    Includes spherical Earth curvature, not refraction or terrain occlusion.
    Unknown altitude/orientation is unknown, never a confirmed zero or match.
    """
    def finite(x):return isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x)
    try:
        lat,lon,alat,alon=[config['latitude'],config['longitude'],aircraft['latitude'],aircraft['longitude']]
        if not all(finite(v) for v in (lat,lon,alat,alon)):return None
        p1,p2=math.radians(lat),math.radians(alat);dl=math.radians(alon-lon)
        h=math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        arc=2*math.asin(math.sqrt(max(0,min(1,h))))
        distance=3440.065*arc
        bearing=math.atan2(math.sin(dl)*math.cos(p2),math.cos(p1)*math.sin(p2)-math.sin(p1)*math.cos(p2)*math.cos(dl))
    except (KeyError,TypeError,ValueError):return None
    fov=field_of_view(config);az=config.get('camera_azimuth_deg');pitch=fov['elevation_deg']
    delta=math.atan2(math.sin(bearing-math.radians(az or 0)),math.cos(bearing-math.radians(az or 0)))
    in_bearing=abs(delta)<=math.radians(fov['azimuth_span_deg']/2) if finite(az) else None
    result=dict(distance_nm=distance,bearing_deg=math.degrees(bearing)%360,in_bearing=in_bearing,
                elevation_deg=None,relative_height_ft=None,in_fov=None)
    altitude=aircraft.get('altitude_ft')
    if not finite(altitude) or not finite(station_altitude_ft):return result
    earth_ft=3440.065*6076.11549
    horizontal=(earth_ft+altitude)*math.sin(arc)
    height=(earth_ft+altitude)*math.cos(arc)-(earth_ft+station_altitude_ft)
    elevation=math.atan2(height,horizontal)
    result.update(elevation_deg=math.degrees(elevation),relative_height_ft=height)
    if not finite(az) or pitch is None:return result
    p=math.radians(pitch);ce=math.cos(elevation);se=math.sin(elevation)
    forward=ce*math.cos(delta)*math.cos(p)+se*math.sin(p)
    right=ce*math.sin(delta);up=se*math.cos(p)-ce*math.cos(delta)*math.sin(p)
    result['in_fov']=forward>0 and abs(right)<=forward*math.tan(math.radians(fov['horizontal_deg']/2)) and abs(up)<=forward*math.tan(math.radians(fov['vertical_deg']/2))
    return result
