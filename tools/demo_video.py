"""Record only a disposable virtual display containing the isolated browser."""
import os
import subprocess
import time

import imageio_ffmpeg


class DemoVideo:
    def __init__(self, directory, browser):
        if os.environ.get('ZEDLINK_SCREENSHOT_ISOLATED_DISPLAY') != '1':
            raise RuntimeError('Recording requires the documented separate Xvfb display')
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.started = time.monotonic()
        self.log = (directory / 'encoding.log').open('w')
        self.encoder = subprocess.Popen([
            imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error',
            '-f', 'x11grab', '-framerate', '30', '-video_size', '1440x900',
            '-draw_mouse', '0', '-i', os.environ['DISPLAY'],
            '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
            '-g', '60', '-threads', '1', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
            '-metadata', 'title=ZedLink walkthrough',
            str(directory / 'zedlink-walkthrough.mp4'),
        ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log)
        browser.save_screenshot(str(directory / 'walkthrough-poster.png'))
        browser.execute_script("""
            const pointer = document.createElement('div');
            pointer.id = 'walkthrough-pointer';
            Object.assign(pointer.style, {position:'fixed',left:'50%',top:'50%',width:'14px',height:'14px',
                border:'2px solid white',borderRadius:'50%',background:'#6ac79e',boxShadow:'0 0 0 4px #6ac79e33',
                transform:'translate(-50%,-50%)',pointerEvents:'none',zIndex:'2147483647',
                transition:'left .45s ease, top .45s ease'});
            document.body.append(pointer);
        """)
        time.sleep(1)

    def click(self, browser, element):
        browser.execute_script("""
            const r=arguments[0].getBoundingClientRect(), p=document.getElementById('walkthrough-pointer');
            p.style.left=(r.left+r.width/2)+'px'; p.style.top=(r.top+r.height/2)+'px';
        """, element)
        time.sleep(.6)
        browser.execute_script("""
            document.getElementById('walkthrough-pointer').animate([
                {boxShadow:'0 0 0 4px #6ac79e99'}, {boxShadow:'0 0 0 22px #6ac79e00'}
            ], {duration:550});
        """)
        element.click()
        time.sleep(.65)

    def type(self, element, text):
        for character in text:
            element.send_keys(character)
            time.sleep(.055)
        time.sleep(.6)

    def scene(self, seconds=2):
        time.sleep(seconds)

    def close(self):
        self.encoder.communicate(input=b'q\n', timeout=30)
        self.log.close()
        if self.encoder.returncode:
            raise RuntimeError('Video encoder failed; inspect encoding.log')
        (self.directory / 'encoding.log').unlink()
        return time.monotonic() - self.started
