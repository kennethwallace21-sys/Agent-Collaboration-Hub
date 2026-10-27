#!/usr/bin/env python3
"""Generate the original collaboration app icon using only Python's stdlib."""

from pathlib import Path
import math
import struct
import zlib

ROOT = Path(__file__).resolve().parent
SIZE = 1024
SCALE = SIZE / 512
pixels = bytearray(SIZE * SIZE * 4)


def blend(x, y, color, opacity=1):
    i = (y * SIZE + x) * 4
    sa = max(0, min(1, opacity))
    da = pixels[i + 3] / 255
    out = sa + da * (1 - sa)
    if not out:
        return
    for c in range(3):
        pixels[i + c] = round((color[c] * sa + pixels[i + c] * da * (1 - sa)) / out)
    pixels[i + 3] = round(out * 255)


def shape(bounds, distance, color, opacity=1):
    x0, y0, x1, y1 = bounds
    for y in range(max(0, int(y0 * SCALE) - 2), min(SIZE, math.ceil(y1 * SCALE) + 2)):
        py = (y + .5) / SCALE
        for x in range(max(0, int(x0 * SCALE) - 2), min(SIZE, math.ceil(x1 * SCALE) + 2)):
            px = (x + .5) / SCALE
            coverage = max(0, min(1, .5 - distance(px, py) * SCALE))
            if coverage:
                blend(x, y, color(px, py) if callable(color) else color, coverage * opacity)


def circle(cx, cy, r, color, opacity=1):
    shape((cx-r, cy-r, cx+r, cy+r), lambda x, y: math.hypot(x-cx, y-cy)-r, color, opacity)


def line(ax, ay, bx, by, width, color, opacity=1):
    dx, dy = bx-ax, by-ay
    length = dx*dx + dy*dy
    def distance(x, y):
        t = max(0, min(1, ((x-ax)*dx+(y-ay)*dy)/length))
        return math.hypot(x-ax-t*dx, y-ay-t*dy)-width/2
    shape((min(ax,bx)-width/2, min(ay,by)-width/2, max(ax,bx)+width/2, max(ay,by)+width/2), distance, color, opacity)


def rounded_rect(x0, y0, x1, y1, radius, color):
    cx, cy = (x0+x1)/2, (y0+y1)/2
    hw, hh = (x1-x0)/2-radius, (y1-y0)/2-radius
    def distance(x, y):
        qx, qy = abs(x-cx)-hw, abs(y-cy)-hh
        return math.hypot(max(qx,0), max(qy,0))+min(max(qx,qy),0)-radius
    shape((x0,y0,x1,y1), distance, color)


def mix(a, b, t):
    return tuple(round(a[i]*(1-t)+b[i]*t) for i in range(3))


def background(x, y):
    color = mix((28,40,66), (10,17,34), (x+y)/1024)
    cyan = .12 * math.exp(-((x-125)**2+(y-96)**2)/40000)
    purple = .09 * math.exp(-((x-430)**2+(y-440)**2)/35000)
    return mix(mix(color, (31,155,169), cyan), (113,66,189), purple)


rounded_rect(0, 0, 512, 512, 114, background)
# A subtle inner keyline keeps the silhouette legible on light and dark desktops.
shape((9,9,503,503), lambda x,y: abs(math.hypot(max(abs(x-256)-141,0),max(abs(y-256)-141,0))+min(max(abs(x-256)-141,abs(y-256)-141),0)-106)-.65, (255,255,255), .08)

# Three independent agents, connected through a human coordinator.
for cx,cy in ((256,132),(150,316),(362,316)):
    line(256,255,cx,cy,22,(118,154,190),.10)
    line(256,255,cx,cy,9,(211,229,246),.85)

agents = [
    (256,132,(92,233,233),(38,184,204)),
    (150,316,(184,163,255),(137,101,240)),
    (362,316,(255,182,134),(245,126,108)),
]
for cx,cy,top,bottom in agents:
    circle(cx,cy+6,59,(3,8,24),.30)
    circle(cx,cy,56,(241,247,255),.20)
    circle(cx,cy,54,lambda x,y,cy=cy,top=top,bottom=bottom: mix(top,bottom,max(0,min(1,(y-cy+54)/108))))
    for ex in (cx-13,cx+13):
        line(ex,cy-5,ex,cy+5,8,(18,32,54),.90)

circle(256,255,40,(7,16,32),.30)
circle(256,255,35,(247,250,255))
circle(256,246,8,(34,49,73))
# A broad, round-shouldered silhouette forms the central human node.
line(245,269,267,269,13,(34,49,73))
circle(256,263,11,(34,49,73))


def resized(size):
    factor = SIZE // size
    assert size * factor == SIZE
    result = bytearray(size * size * 4)
    count = factor * factor
    for y in range(size):
        for x in range(size):
            totals = [0,0,0,0]
            # Average premultiplied color to retain clean transparent edges.
            for sy in range(y*factor,(y+1)*factor):
                i = (sy*SIZE+x*factor)*4
                for sx in range(factor):
                    p = i+sx*4
                    a = pixels[p+3]
                    totals[3] += a
                    for c in range(3):
                        totals[c] += pixels[p+c]*a
            j = (y*size+x)*4
            if totals[3]:
                for c in range(3):
                    result[j+c] = round(totals[c]/totals[3])
                result[j+3] = round(totals[3]/count)
    return result


def chunk(tag, data):
    return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)


def png(size):
    rgba = resized(size)
    scanlines = b''.join(b'\0'+rgba[y*size*4:(y+1)*size*4] for y in range(size))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(scanlines,9))+chunk(b'IEND',b'')


images = {size:png(size) for size in (16,32,64,128,256,512)}
for size in (256,512):
    (ROOT/f'app-icon-{size}.png').write_bytes(images[size])

# Windows supports PNG data inside ICO entries; a zero width denotes 256.
ico_sizes = (16,32,64,128,256)
offset = 6+16*len(ico_sizes)
entries = []
for size in ico_sizes:
    data = images[size]
    entries.append(struct.pack('<BBBBHHII',size%256,size%256,0,0,1,32,len(data),offset))
    offset += len(data)
(ROOT/'app-icon.ico').write_bytes(struct.pack('<HHH',0,1,len(ico_sizes))+b''.join(entries)+b''.join(images[s] for s in ico_sizes))

# macOS ICNS: ic08 and ic09 hold the native 256 and 512 pixel PNGs.
icns_chunks = b''.join(tag+struct.pack('>I',8+len(images[size]))+images[size] for tag,size in ((b'ic08',256),(b'ic09',512)))
(ROOT/'app-icon.icns').write_bytes(b'icns'+struct.pack('>I',8+len(icns_chunks))+icns_chunks)
print('Generated app-icon-256.png, app-icon-512.png, app-icon.ico, app-icon.icns')
