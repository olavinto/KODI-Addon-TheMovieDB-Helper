from tmdbhelper.lib.addon.plugin import get_setting, get_condvisibility
from jurialmunkey.window import get_property, wait_for_property, get_current_window
from tmdbhelper.lib.monitor.cronjob import CronJobMonitor
from tmdbhelper.lib.monitor.listitem import ListItemMonitorFunctions, ListItemInfoGetter, CV_USE_LISTITEM, CV_USE_LOCAL_CONTAINER
from tmdbhelper.lib.monitor.player import PlayerMonitor
from tmdbhelper.lib.monitor.update import UpdateMonitor
from tmdbhelper.lib.monitor.images import ImageManipulations
from threading import Thread


ON_SERVICE_ENABLED = (
    "!Skin.HasSetting(TMDbHelper.Service) + "
    "!Skin.HasSetting(TMDbHelper.EnableBlur) + "
    "!Skin.HasSetting(TMDbHelper.EnableDesaturate) + "
    "!Skin.HasSetting(TMDbHelper.EnableColors)")

ON_MODAL = (
    "["
    "Window.IsVisible(DialogSelect.xml) | "
    "Window.IsVisible(progressdialog) | "
    "Window.IsVisible(busydialog) | "
    "Window.IsVisible(shutdownmenu) | "
    "!String.IsEmpty(Window.Property(TMDbHelper.ServicePause))"
    "]")

ON_INFODIALOG = (
    "["
    "Window.IsVisible(movieinformation) | "
    "Window.IsVisible(musicinformation) | "
    "Window.IsVisible(songinformation) | "
    "Window.IsVisible(addoninformation) | "
    "Window.IsVisible(pvrguideinfo) | "
    "Window.IsVisible(tvchannels) | "
    "Window.IsVisible(tvguide)"
    "]")

ON_LISTITEM = (
    "["
    "Window.IsMedia | "
    "!String.IsEmpty(Window(Home).Property(TMDbHelper.WidgetContainer)) | "
    "!String.IsEmpty(Window.Property(TMDbHelper.WidgetContainer))"
    "] | ") + ON_INFODIALOG

ON_FULLSCREEN_LISTITEM = (
    "["
    "Skin.HasSetting(TMDbHelper.UseLocalWidgetContainer) + "
    "!String.IsEmpty(Window.Property(TMDbHelper.WidgetContainer))"
    "] | ") + ON_INFODIALOG

ON_SCROLL = "Container.Scrolling"

ON_CONTEXT = (
    "Window.IsVisible(contextmenu) | "
    "!String.IsEmpty(Window.Property(TMDbHelper.ContextMenu))")

ON_SCREENSAVER = "System.ScreenSaverActive"

ON_FULLSCREEN = "Window.IsVisible(fullscreenvideo)"


class Poller():
    def _on_idle(self, wait_time=30):
        self.update_monitor.waitForAbort(wait_time)

    def _on_fullscreen(self):
        self._on_idle(1)

    def _on_modal(self):
        self._on_idle(1)

    def _on_context(self):
        self._on_idle(1)

    def _on_scroll(self):
        self._on_idle(0.2)

    def _on_listitem(self):
        self._on_idle(0.2)

    def _on_clear(self):
        self._on_idle(0.2)

    def _on_exit(self):
        return

    def poller(self):
        while not self.update_monitor.abortRequested() and not self.exit:
            if get_property('ServiceStop'):
                self.exit = True

            # If we're in fullscreen video then we should update the playermonitor time
            elif get_condvisibility(ON_FULLSCREEN):
                self._on_fullscreen()

            # Sit idle in a holding pattern if the skin doesn't need the service monitor yet
            elif get_condvisibility(ON_SERVICE_ENABLED):
                self._on_idle(30)

            # Sit idle in a holding pattern if screen saver is active
            elif get_condvisibility(ON_SCREENSAVER):
                self._on_idle(2)

            # skip when modal or busy dialogs are opened (e.g. select / progress / busy etc.)
            elif get_condvisibility(ON_MODAL):
                self._on_modal()

            # manage context menu separately from other modals to pass info through
            elif get_condvisibility(ON_CONTEXT):
                self._on_context()

            # skip when container scrolling
            elif get_condvisibility(ON_SCROLL):
                self._on_scroll()

            # media window is opened or widgetcontainer set - start listitem monitoring!
            elif get_condvisibility(ON_LISTITEM):
                self._on_listitem()

            # Otherwise just sit here and wait
            else:
                self._on_clear()

        # Some clean-up once service exits
        self._on_exit()


class ImagesMonitor(Thread, ListItemInfoGetter, ImageManipulations, Poller):
    def __init__(self, update_monitor):
        Thread.__init__(self)
        self.exit = False
        self.update_monitor = update_monitor
        self.crop_image_cur = None
        self.blur_image_cur = None
        self.pre_item = None
        self._readahead_li = get_setting('service_listitem_readahead')  # Allows readahead queue of next ListItems when idle

    @property
    def cur_item(self):
        return self.get_item_identifier()

    @property
    def container_item(self):
        window_id = get_current_window() if get_condvisibility(CV_USE_LOCAL_CONTAINER) else None
        widget_id = get_property('WidgetContainer', window_id=window_id, is_type=int)
        container = f'Container({widget_id}).' if widget_id else 'Container.'
        return 'ListItem.' if get_condvisibility(CV_USE_LISTITEM) else f'{container}ListItem({{}}).'

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


class ServiceMonitor(Poller):
    def __init__(self):
        self.exit = False
        self.listitem = None

    def run(self):
        self.update_monitor = UpdateMonitor()
        self.player_monitor = PlayerMonitor()

        self.cron_job = CronJobMonitor(self.update_monitor, update_hour=get_setting('library_autoupdate_hour', 'int'))
        self.cron_job.setName('Cron Thread')
        self.cron_job.start()

        self.images_monitor = ImagesMonitor(self.update_monitor)
        self.images_monitor.setName('Image Thread')
        self.images_monitor.start()

        self.listitem_funcs = ListItemMonitorFunctions()
        self.listitem_funcs.images_monitor = self.images_monitor

        get_property('ServiceStarted', 'True')

        self.poller()

    def _on_listitem(self):
        self.listitem_funcs.on_listitem()
        self._on_idle(0.2)

    def _on_scroll(self):
        self.listitem_funcs.on_scroll()
        self._on_idle(0.2)

    def _on_player(self):
        if self.player_monitor.isPlayingVideo():
            self.player_monitor.current_time = self.player_monitor.getTime()

    def _on_fullscreen(self):
        self._on_player()
        if get_condvisibility(ON_FULLSCREEN_LISTITEM):
            return self._on_listitem()
        self._on_idle(1)

    def _on_context(self):
        self.listitem_funcs.on_context_listitem()
        self._on_idle(1)

    def _on_clear(self):
        """
        IF we've got properties to clear lets clear them and then jump back in the loop
        Otherwise we should sit for a second so we aren't constantly polling
        """
        if self.listitem_funcs.properties or self.listitem_funcs.index_properties:
            return self.listitem_funcs.clear_properties()
        self.listitem_funcs.blur_fallback()
        self._on_idle(1)

    def _on_exit(self):
        self.cron_job.exit = True
        if not self.update_monitor.abortRequested():
            get_property('ServiceStarted', clear_property=True)
            get_property('ServiceStop', clear_property=True)
        del self.images_monitor
        del self.player_monitor
        del self.update_monitor
        del self.listitem_funcs


def restart_service_monitor():
    if get_property('ServiceStarted') == 'True':
        wait_for_property('ServiceStop', value='True', set_property=True)  # Stop service
    wait_for_property('ServiceStop', value=None)  # Wait until Service clears property
    Thread(target=ServiceMonitor().run).start()
