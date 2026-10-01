import numpy as np

class NestedBuffer:
    def __init__(self, width=1024, height=768, display_rect=(100, 100, 640, 480)):
        """
        Nested buffer for compositing metadata and a video display zone.
        :param width: Total frame width
        :param height: Total frame height
        :param display_rect: Tuple of (x, y, w, h) for the video display zone
        """
        self.width = width
        self.height = height
        self.display_rect = display_rect
        self.frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # System Time (master execution tick)
        self.system_tick = 0
        
        # Media Time (nested video 24 FPS)
        self.media_tick = 0
        self.media_fps = 24.0
        
        # Metadata
        self.volume = 1.0
        self.fps = 60.0
        
        self.video_frames = []

    def set_video_source(self, frames):
        """Set the video frames for playback."""
        self.video_frames = frames

    def advance_system_time(self, ticks=1):
        """Advance the master execution System Time independently."""
        self.system_tick += ticks

    def advance_media_time(self, frames=1):
        """Advance the Media Time independently."""
        self.media_tick += frames

    def seek_media_time(self, seconds):
        """Seekable Media Time."""
        self.media_tick = int(seconds * self.media_fps)
        if self.video_frames:
            self.media_tick = max(0, min(self.media_tick, len(self.video_frames) - 1))

    def get_current_video_frame(self):
        """Get the current video frame based on Media Time."""
        if not self.video_frames:
            return np.zeros((self.display_rect[3], self.display_rect[2], 3), dtype=np.uint8)
        
        idx = self.media_tick
        if idx >= len(self.video_frames):
            idx = len(self.video_frames) - 1
            
        return self.video_frames[idx]

    def _render_metadata_zone(self):
        """
        Renders metadata (playhead time, volume, FPS) into a specific metadata zone.
        We use the top row of pixels as the metadata zone for simplicity.
        """
        # Clear metadata zone (top row)
        self.frame[0, :, :] = 0
        
        # Pixel 0: System Tick (encode as RGB bytes)
        self.frame[0, 0] = [
            (self.system_tick >> 16) & 0xFF,
            (self.system_tick >> 8) & 0xFF,
            self.system_tick & 0xFF
        ]
        
        # Pixel 1: Media Tick
        self.frame[0, 1] = [
            (self.media_tick >> 16) & 0xFF,
            (self.media_tick >> 8) & 0xFF,
            self.media_tick & 0xFF
        ]
        
        # Pixel 2: Volume (0-255)
        self.frame[0, 2] = [
            int(self.volume * 255),
            0,
            0
        ]
        
        # Pixel 3: FPS (0-255)
        self.frame[0, 3] = [
            int(self.fps),
            0,
            0
        ]

    def parse_metadata_zone(self):
        """
        Parses the metadata zone to verify it's rendered correctly.
        Returns a dictionary of parsed values.
        """
        # Pixel 0: System Tick
        sys_tick_rgb = self.frame[0, 0]
        sys_tick = (sys_tick_rgb[0] << 16) | (sys_tick_rgb[1] << 8) | sys_tick_rgb[2]
        
        # Pixel 1: Media Tick
        med_tick_rgb = self.frame[0, 1]
        med_tick = (med_tick_rgb[0] << 16) | (med_tick_rgb[1] << 8) | med_tick_rgb[2]
        
        # Pixel 2: Volume
        vol_rgb = self.frame[0, 2]
        volume = vol_rgb[0] / 255.0
        
        # Pixel 3: FPS
        fps_rgb = self.frame[0, 3]
        fps = float(fps_rgb[0])
        
        return {
            "system_tick": sys_tick,
            "media_tick": med_tick,
            "volume": volume,
            "fps": fps
        }

    def blit(self, source, rect):
        """Blit nested video frames into the display zone."""
        x, y, w, h = rect
        # ensure boundaries
        x2, y2 = min(x + w, self.width), min(y + h, self.height)
        
        # If source is smaller or larger, we just copy what fits
        src_h, src_w = source.shape[:2]
        copy_w = min(w, src_w, x2 - x)
        copy_h = min(h, src_h, y2 - y)
        
        self.frame[y:y+copy_h, x:x+copy_w] = source[:copy_h, :copy_w]

    def composite(self):
        """
        Composites metadata and display zones into a final renderable frame.
        """
        self.frame.fill(0)
        
        self._render_metadata_zone()
        
        vid_frame = self.get_current_video_frame()
        self.blit(vid_frame, self.display_rect)
        
        return self.frame
