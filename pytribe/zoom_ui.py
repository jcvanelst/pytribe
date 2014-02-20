import time
import threading
import Queue
import wx
from bufferedcanvas import BufferedCanvas
import pytribe
import pyHook
from ScreenShotWX import screencapture




def current_bitmap(zoom_map):

    zm = zoom_map
    bitmap = zm.base_bitmap
    yield bitmap
    while True:
        #gaze_data = pytribe.query_tracker()
        #if gaze_data is not None:
        #    gaze_avg_dict = gaze_data['values']['frame']['avg']
        #    gaze_avg = (gaze_avg_dict['x'],gaze_avg_dict['y'])
        #else:
        #    gaze_avg = zm.base_center
        zm.zoom_in(zoom_factor=1.05)
        bitmap = zm.zoom_bitmap #  scale_bitmap(bitmap, 400*x, 400*x)
        yield bitmap

def parse_center(data_queue, default=None):
    gaze_data_update = pytribe.extract_queue(data_queue)
    if len(gaze_data_update) > 0:
        center_dict = gaze_data_update[-1]['values']['frame']['avg']
        center = (center_dict['x'], center_dict['y'])
    else:
        center = default
    return center

class ZoomMap(object):
    """Contains original bitmap, plus transformed zoom coordinates.

    Methods allow for translation between "base" coordinates and "zoom" coordinates"""
    def __init__(self, center=(400,400), size=(400,400), data_queue=None):

        self.base_center = center
        self.base_size = size
        self.base_width = size[0]*1.0
        self.base_height = size[1]*1.0
        self.data_q = data_queue

        self.current_zoom_factor = 1.0
        self.zoom_center_offset_x = 0.0
        self.zoom_center_offset_y = 0.0

        self.base_loc = (int(center[0] - size[0]/2.0),
                         int(center[1] - size[1]/2.0))
        self.previous_center = center

        #TODO: Handle case where base_loc +size includes areas outside of the screen?
        if self.base_loc[0] < 0: self.base_loc = (0, self.base_loc[1])
        if self.base_loc[1] < 0: self.base_loc = (self.base_loc[0], 0)

        self.base_bitmap = screencapture(self.base_loc, self.base_size)
        self.zoom_bitmap = self.base_bitmap
        self.base_image = wx.ImageFromBitmap(self.base_bitmap)


    def zoom_size_px(self):
        return (self.base_width * self.current_zoom_factor,
                self.base_height * self.current_zoom_factor)

    def rel_zoom_loc(self):
        zsp = self.zoom_size_px()
        return (self.zoom_center_offset_x * self.current_zoom_factor +
                (zsp[0] - self.base_width)/2.0,
                self.zoom_center_offset_y * self.current_zoom_factor +
                (zsp[1] - self.base_width)/2.0)

    def zoom_in(self, zoom_factor=1.05, zoomed_coords=True):

        gaze_data_update = parse_center(self.data_q)
        if gaze_data_update not in [None, (0,0)]:
            self.previous_center = gaze_data_update

        center = self.previous_center

        self.current_zoom_factor *= zoom_factor

        zoom_pan_speed = 0.2

        self.zoom_center_offset_x += (zoom_pan_speed *
                                      (center[0] - self.base_center[0]) /
                                      self.current_zoom_factor)
        self.zoom_center_offset_y += (zoom_pan_speed *
                                      (center[1] - self.base_center[1]) /
                                      self.current_zoom_factor)


        #width/height to scale new image to
        _width, _height = self.zoom_size_px()

        #Amount to shift new image down/right before scaling up
        _x_offset, _y_offset = self.rel_zoom_loc()

        #Prevent zooming outside of original box
        if _x_offset < 0: _x_offset = 0
        if _y_offset < 0: _y_offset = 0
        if _x_offset + self.base_size[0] > _width:
            _x_offset = _width - self.base_size[0]
        if _y_offset + self.base_size[1] > _height:
            _y_offset = _height - self.base_size[1]

        #Rect can be replaced by x,y,width,height tuple
        #sub_image = self.base_image.GetSubImage((_x_offset, _y_offset, _width, _height))
        print center
        print self.zoom_center_offset_x, self.zoom_center_offset_y
        print _x_offset, _y_offset, _width, _height, self.zoom_size_px()
        #Changes image in-place to
        #sub_image = self.base_image
        #sub_image.Resize(size=(_width, _height), pos=(-2, -2))

        zoomed_image = self.base_image.Scale(_width, _height,
                                             wx.IMAGE_QUALITY_NORMAL)
        sub_image = zoomed_image.GetSubImage((_x_offset, _y_offset,
                                              self.base_size[0], self.base_size[1]))

        self.zoom_bitmap = wx.BitmapFromImage(sub_image)


class ZoomCanvas(BufferedCanvas):

    def __init__(self, *args, **kwargs):
        #Initialization of bitmap_gen MUST come first
        self.bitmap_gen = current_bitmap(kwargs.pop('zoom_map'))
        BufferedCanvas.__init__(self, *args, **kwargs)

    def draw(self, dc):
        dc.DrawBitmap(next(self.bitmap_gen), 0, 0)

    def reset(self, zoom_map):
        self.bitmap_gen = current_bitmap(zoom_map)
        self.update()


class ZoomFrame(wx.Frame):

    """Main Frame holding the Panel."""
    def __init__(self, *args,  **kwargs):
        self.tick_ms = kwargs.pop('tick_ms', 125) # Remove non-standard kwargs
        self.data_q = kwargs.pop('data_queue', None)
        wx.Frame.__init__(self, *args, **kwargs)

        self.raw_data_q = Queue.Queue()
        self.key_now_down = False

        #First argument is "parent" (ZoomFrame here), second is "ID"
        #self.canvas = ZoomCanvas(self, wx.ID_ANY,
        #                         size=kwargs['size'])
        #self.canvas.bitmap = wx.Bitmap('400x400_test.bmp')
        self.Bind(wx.EVT_CLOSE, self.onClose)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.update_zoom, self.timer)
        self.canvas = ZoomCanvas(self, wx.ID_ANY,
                                 size=(400,400),
                                 zoom_map=ZoomMap(center=(400,400),
                                                  size=(400,400)))



        #self.timer.Start(self.tick_ms)


    def on_key_down_event(self, event):
        if event.Key == 'Numlock' and not self.key_now_down:  # \ key = Oem_5

            gaze_avg = parse_center(self.data_q)
            print "Initial Base Target: " + gaze_avg
            if gaze_avg is not None:
                zm = ZoomMap(center=gaze_avg, size=(400, 400),
                             data_queue=self.data_q)
                self.SetSize(zm.base_size)
                self.SetPosition(zm.base_loc)
                self.key_now_down = True
                self.canvas.reset(zm)
                self.timer.Start(self.tick_ms)
                self.Show()
                print "key down"

        return True  # for pass through key events, False to eat Keys

    def update_zoom(self, event):  # This "event" is required...
        self.canvas.update()

    def on_key_up_event(self, event):

        self.key_now_down = False
        self.Hide()
        self.timer.Stop()
        return True

    def onClose(self, event):
        self.timer.Stop()
        self.query_thread.stop()
        self.Show(False)
        self.Destroy()


def main():


    data_q = Queue.Queue()

    app = wx.App(False)
    frame = ZoomFrame(None,
                      wx.ID_ANY,
                      title="Zoom Frame",
                      style=wx.BORDER_NONE | wx.STAY_ON_TOP | wx.FRAME_NO_TASKBAR,
                      tick_ms=40,
                      data_queue=data_q)


    hm = pyHook.HookManager()
    hm.KeyDown = frame.on_key_down_event
    hm.KeyUp = frame.on_key_up_event
    hm.HookKeyboard()

    data_thread = threading.Thread(target=pytribe.queue_tracker_frames,
                                   args=(data_q, None, 0.02))
    data_thread.daemon = True
    data_thread.start()

    #frame.Show()
    app.MainLoop()

if __name__ == '__main__':
    main()

