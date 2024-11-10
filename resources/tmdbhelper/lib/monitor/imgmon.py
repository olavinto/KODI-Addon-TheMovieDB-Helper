from tmdbhelper.lib.monitor.images import ImageManipulations
from tmdbhelper.lib.monitor.poller import Poller
from tmdbhelper.lib.monitor.listitemtools import ListItemInfoGetter
# from tmdbhelper.lib.addon.plugin import get_setting
from threading import Thread


class ImagesMonitor(Thread, ListItemInfoGetter, ImageManipulations, Poller):
    def __init__(self, update_monitor):
        Thread.__init__(self)
        self.exit = False
        self.update_monitor = update_monitor
        self.crop_image_cur = None
        self.blur_image_cur = None
        self.pre_item = None
        self._readahead_li = True  # get_setting('service_listitem_readahead')  # Allows readahead queue of next ListItems when idle

    def setup_current_container(self):
        self._container_item = self.container_item

    def _on_listitem(self):
        self.setup_current_container()
        if self.pre_item != self.cur_item:
            self.get_image_manipulations(use_winprops=True)
            self.pre_item = self.cur_item
        self._on_idle(0.2)

    def _on_scroll(self):
        if self._readahead_li:
            return self._on_listitem()
        self._on_idle(0.2)

    def run(self):
        self.poller()
