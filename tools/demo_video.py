"""Encode an isolated browser UI tour; never record the host desktop."""
from io import BytesIO
from pathlib import Path
import subprocess
import time

from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg


class DemoVideo:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.frames = 0
        self.width, self.height, self.fps = 1440, 1000, 4
        self.font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 22)
        self.heading = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 30)
        self.log = (directory / 'encoding.log').open('w')
        self.encoder = subprocess.Popen([
            imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error',
            '-f', 'rawvideo', '-vcodec', 'rawvideo', '-pix_fmt', 'rgb24',
            '-s', f'{self.width}x{self.height}', '-r', str(self.fps), '-i', '-',
            '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-g', '1', '-threads', '1',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
            '-metadata', 'title=ZedLink isolated interface walkthrough',
            str(directory / 'zedlink-walkthrough.mp4'),
        ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log)

    def frame(self, png, caption):
        canvas = Image.new('RGB', (self.width, self.height), '#07090b')
        draw = ImageDraw.Draw(canvas)
        draw.text((24, 16), 'ZEDLINK', font=self.heading, fill='#eeeeee')
        draw.text((24, 57), caption, font=self.font, fill='#bfc7ce')
        draw.text((1200, 25), 'UI DEMO', font=self.font, fill='#6ac79e')
        draw.line((24, 95, self.width - 24, 95), fill='#2b3934', width=2)
        screenshot = Image.open(BytesIO(png)).convert('RGB')
        screenshot.thumbnail((self.width - 48, self.height - 160), Image.Resampling.LANCZOS)
        canvas.paste(screenshot, ((self.width - screenshot.width) // 2, 108))
        draw.text((24, self.height - 35), 'Isolated demo project / profile · Synthetic conversation and terminal data',
                  font=self.font, fill='#8d979f')
        if self.frames == 0:
            canvas.save(self.directory / 'walkthrough-poster.png', optimize=True)
        self.encoder.stdin.write(canvas.tobytes())
        self.frames += 1

    def scene(self, browser, caption, seconds=4):
        for _ in range(int(seconds * self.fps)):
            started = time.monotonic()
            self.frame(browser.get_screenshot_as_png(), caption)
            time.sleep(max(0, 1 / self.fps - (time.monotonic() - started)))

    def still(self, path, caption, seconds=4):
        png = Path(path).read_bytes()
        for _ in range(int(seconds * self.fps)):
            self.frame(png, caption)

    def close(self):
        self.encoder.stdin.close()
        status = self.encoder.wait(timeout=60)
        self.log.close()
        if status:
            raise RuntimeError('Video encoder failed; inspect encoding.log')
        (self.directory / 'encoding.log').unlink()
        return self.frames / self.fps
