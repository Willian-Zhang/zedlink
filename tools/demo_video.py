"""Capture an isolated kiosk continuously, with readable chapters outside the UI."""
import json
import os
import subprocess
import time
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont


class DemoVideo:
    def __init__(self, directory, browser, width=1440, height=900, fps=60):
        if os.environ.get('ZEDLINK_SCREENSHOT_ISOLATED_DISPLAY') != '1':
            raise RuntimeError('Recording requires a separate Xvfb display')
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        self.chapters = []
        self.width = width
        self.started = time.monotonic()
        self.log = (directory / 'encoding.log').open('w')
        self.raw = directory / '.capture.mp4'
        self.encoder = subprocess.Popen([
            self.ffmpeg, '-y', '-loglevel', 'warning', '-f', 'x11grab',
            '-framerate', str(fps), '-video_size', f'{width}x{height}', '-draw_mouse', '0',
            '-i', os.environ['DISPLAY'], '-an', '-c:v', 'libx264', '-preset', 'veryfast',
            '-crf', '18', '-g', str(fps*2), '-threads', '4', '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart', str(self.raw),
        ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log)
        browser.save_screenshot(str(directory / 'walkthrough-poster.png'))
        browser.execute_script("""
            const pointer = document.createElement('div'); pointer.id = 'walkthrough-pointer';
            Object.assign(pointer.style, {position:'fixed',left:'48%',top:'50%',width:'18px',height:'24px',
                background:'white',clipPath:'polygon(0 0, 0 100%, 28% 75%, 50% 100%, 65% 92%, 44% 68%, 90% 68%)',
                filter:'drop-shadow(0 1px 2px black)',pointerEvents:'none',zIndex:'2147483647',
                transition:'left .65s cubic-bezier(.22,.61,.36,1), top .65s cubic-bezier(.22,.61,.36,1)'});
            document.body.append(pointer);
        """)
        time.sleep(1)

    def chapter(self, title):
        self.chapters.append({'at': round(time.monotonic()-self.started, 3), 'title': title})
        (self.directory/'chapters.json').write_text(json.dumps(self.chapters,indent=2)+'\n')
        print('Recording:', title, flush=True)

    def click(self, browser, element):
        browser.execute_script("""
            arguments[0].scrollIntoView({block:'nearest',behavior:'smooth'});
        """, element)
        time.sleep(.3)
        browser.execute_script("""
            const r=arguments[0].getBoundingClientRect(), p=document.getElementById('walkthrough-pointer');
            (arguments[0].closest('dialog[open]') || document.body).append(p);
            p.style.left=(r.left+r.width/2)+'px'; p.style.top=(r.top+r.height/2)+'px';
        """, element)
        time.sleep(.75)
        browser.execute_script("""
            const r=arguments[0].getBoundingClientRect(), ring=document.createElement('div');
            Object.assign(ring.style,{position:'fixed',left:(r.left+r.width/2-16)+'px',top:(r.top+r.height/2-16)+'px',
                width:'32px',height:'32px',border:'2px solid #b6c7dc',borderRadius:'50%',pointerEvents:'none',zIndex:'2147483646'});
            (arguments[0].closest('dialog[open]') || document.body).append(ring); ring.animate([{transform:'scale(.5)',opacity:.9},{transform:'scale(1.3)',opacity:0}],{duration:450}).onfinish=()=>ring.remove();
        """, element)
        element.click()
        time.sleep(.8)

    def type(self, element, text):
        for character in text:
            element.send_keys(character)
            time.sleep(.07)
        time.sleep(.7)

    def scene(self, seconds=2):
        time.sleep(seconds)

    def close(self):
        self.encoder.communicate(input=b'q\n', timeout=30)
        duration = time.monotonic()-self.started
        self.log.close()
        if self.encoder.returncode:
            raise RuntimeError('Capture failed; inspect encoding.log')
        filters=['[0:v]pad=iw:ih+68:0:68:color=0x101216[base0]']
        files=[]
        inputs=[]
        for index, chapter in enumerate(self.chapters):
            text=self.directory/f'.chapter-{index}.png'
            image=Image.new('RGB',(self.width,68),'#101216')
            draw=ImageDraw.Draw(image)
            draw.text((24,18),f'{index+1:02d}   {chapter["title"]}',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',24),fill='white')
            image.save(text); files.append(text); inputs.extend(['-loop','1','-framerate','1','-i',str(text)])
            start=0 if index==0 else chapter['at']; end=self.chapters[index+1]['at'] if index+1<len(self.chapters) else duration
            filters.append(f"[base{index}][{index+1}:v]overlay=0:0:shortest=1:enable='between(t,{start},{end})'[base{index+1}]")
        subprocess.run([self.ffmpeg,'-y','-loglevel','error','-i',str(self.raw),*inputs,'-filter_complex_threads','2','-filter_complex',';'.join(filters),'-map',f'[base{len(self.chapters)}]','-an','-c:v','libx264','-preset','fast','-crf','18','-threads','4','-pix_fmt','yuv420p','-movflags','+faststart','-metadata','title=ZedLink',str(self.directory/'zedlink-in-action.mp4')],check=True)
        (self.directory/'chapters.json').write_text(json.dumps(self.chapters,indent=2)+'\n')
        for path in files: path.unlink()
        self.raw.unlink()
        return duration
