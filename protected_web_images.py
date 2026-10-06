"""Public derivatives only. Source bytes are never returned from public routes."""
from io import BytesIO
from PIL import Image, ImageDraw, ImageOps, ImageFont


def derivative(source, *, max_edge=1800, watermark=False, opacity='Low', position='corner', output_format='JPEG'):
    if max_edge not in (1200,1600,1800,2000,2400):
        raise ValueError('Unsupported public image limit.')
    with Image.open(source) as original:
        original.load()
        image=ImageOps.exif_transpose(original).convert('RGB')
        # Retain a source ICC profile for colour fidelity, never EXIF or GPS.
        profile=original.info.get('icc_profile')
    image.thumbnail((max_edge,max_edge),Image.Resampling.LANCZOS)
    if watermark:
        overlay=Image.new('RGBA',image.size)
        draw=ImageDraw.Draw(overlay)
        alpha={'Low':45,'Medium':90,'High':140}[opacity]
        text='SPORTS CAVE'
        font=ImageFont.load_default(size=max(14,max(image.size)//55))
        bounds=draw.textbbox((0,0),text,font=font)
        text_width,text_height=bounds[2]-bounds[0],bounds[3]-bounds[1]
        if position=='repeated':
            for y in range(20,image.height,max(90,text_height*7)):
                for x in range(20,image.width,max(160,text_width+50)):draw.text((x,y),text,fill=(255,255,255,alpha),font=font)
        else:
            point=(max(10,image.width-text_width-20),max(10,image.height-text_height-20)) if position=='corner' else (max(0,(image.width-text_width)//2),max(0,(image.height-text_height)//2))
            draw.text(point,text,fill=(255,255,255,alpha),font=font)
        image=Image.alpha_composite(image.convert('RGBA'),overlay).convert('RGB')
    result=BytesIO()
    if output_format not in ('JPEG','WEBP','PNG'):
        raise ValueError('Unsupported derivative format.')
    image.save(result,output_format,quality=85,optimize=True,icc_profile=profile)
    return result.getvalue()


def write_public_derivative(source,destination):
    from pathlib import Path
    from security_protection import DEFAULTS, cached_policy
    source,destination=Path(source),Path(destination)
    if source.resolve()==destination.resolve():
        raise ValueError('A public derivative cannot overwrite its source.')
    try:policy=cached_policy()
    except Exception:policy=DEFAULTS
    formats={'.webp':'WEBP','.jpg':'JPEG','.jpeg':'JPEG','.png':'PNG'}
    output=derivative(source,max_edge=policy['maxImageEdge'],watermark=policy['visibleWatermark'],opacity=policy['watermarkOpacity'],position=policy['watermarkPosition'],output_format=formats[destination.suffix.lower()])
    import os, tempfile
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent,delete=False) as temporary:
        temporary.write(output)
        temporary_path=temporary.name
    try:os.replace(temporary_path,destination)
    finally:
        if os.path.exists(temporary_path):os.unlink(temporary_path)
    return destination


def classify_public_image(width,height,filename='',max_edge=1800):
    name=str(filename).casefold()
    if any(word in name for word in ('master','.psd','.tif','print-ready','print_ready')):
        return 'REVIEW'
    if max(int(width or 0),int(height or 0))>max_edge:
        return 'HIGH RESOLUTION PUBLIC IMAGE'
    return 'SAFE' if width and height else 'REVIEW'
