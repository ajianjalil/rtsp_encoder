#!/usr/bin/python
# --------------------------------------------------------------------------- #
# Supporting arguments
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Use gi to import GStreamer functionality
# --------------------------------------------------------------------------- #
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
gi.require_version('GstVideo', '1.0')
import argparse
import logging
import json
import time
import os.path
import subprocess
import signal
import sys
from ctypes import *
from gi.repository import GObject, Gst, Gio, GstVideo, GstRtspServer, GLib
from threading import Thread, Lock
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
gi.require_version('GstVideo', '1.0')
parser = argparse.ArgumentParser(description="gst-rtsp-launch-py V0.2")
parser.add_argument('-v', '--verbose', action='store_true',
                    help='Make script chatty')
args = parser.parse_args()
import threading

# --------------------------------------------------------------------------- #
# configure the service logging
# --------------------------------------------------------------------------- #
logging.basicConfig()
log = logging.getLogger()

# --------------------------------------------------------------------------- #
# import misc standard libraries
# --------------------------------------------------------------------------- #


if args.verbose:
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.INFO)

# def on_debug(category, level, dfile, dfctn, dline, source, message, user_data):
#     if source:
#         print('Debug {} {}'.format(
#             Gst.DebugLevel.get_name(level), message.get()))
#     else:
#         print('Debug {}: {}'.format(
#             Gst.DebugLevel.get_name(level), message.get()))

# if not Gst.debug_is_active():
#     Gst.debug_set_active(True)
#     level = Gst.debug_get_default_threshold()
#     Gst.debug_set_default_threshold(Gst.DebugLevel.INFO)
#     if level < Gst.DebugLevel.ERROR:
#         Gst.debug_set_default_threshold(Gst.DebugLevel.WARNING)
#     Gst.debug_add_log_function(on_debug, None)
#     Gst.debug_remove_log_function(Gst.debug_log_default)

cam_mutex = Lock()
# -------------------

class LoaderScreen():

    def __init__(self) -> None:
        Gst.init(None)
        pipeline_str = 'videotestsrc pattern=smpte-rp-219 ! video/x-raw, width=1920, height=1080, framerate=10/1 ! textoverlay text="AIVS Loading" valignment=center halignment=center font-desc="Sans, 90" scale-mode=display ! x264enc ! rtph264pay ! tee name=t ! queue ! udpsink host=127.0.0.1 port=15001 t. ! queue ! udpsink host=127.0.0.1 port=15002 t. ! queue ! udpsink host=127.0.0.1 port=15003 t. ! queue ! udpsink host=127.0.0.1 port=15004 t. ! queue ! udpsink host=127.0.0.1 port=15005 t. ! queue ! udpsink host=127.0.0.1 port=15006 t. ! queue ! udpsink host=127.0.0.1 port=15007 t. ! queue ! udpsink host=127.0.0.1 port=15008 t. ! queue ! udpsink host=127.0.0.1 port=15009 t. ! queue ! udpsink host=127.0.0.1 port=15010 t. ! queue ! udpsink host=127.0.0.1 port=15011 t. ! queue ! udpsink host=127.0.0.1 port=15012'
        self.pipeline = Gst.parse_launch(pipeline_str)
        self.bus = self.pipeline.get_bus()
        self.thread = threading.Thread(target=self.play_pipeline)
        self.stop_event = threading.Event()

    def start(self):
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def play_pipeline(self):
        
        self.pipeline.set_state(Gst.State.PLAYING)
        while True:
            message = self.bus.timed_pop_filtered(10000, Gst.MessageType.ANY)
            if message:
                if message.type == Gst.MessageType.ERROR:
                    error = message.parse_error()
                    print(f"Error: {error[1].message}")
                    break
                elif message.type == Gst.MessageType.EOS:
                    print("End of Stream")
                    break
            if self.stop_event.is_set():
                self.pipeline.set_state(Gst.State.PAUSED)
                time.sleep(0.1)
                self.pipeline.set_state(Gst.State.READY)
                time.sleep(0.1)
                self.pipeline.set_state(Gst.State.NULL)
                time.sleep(0.1)
                break
        self.pipeline.set_state(Gst.State.NULL)
        print("Done")
        # Wait for the pipeline thread to finish
        
    
    def post_eos(self):
        eos_message = Gst.Message.new_eos(self.pipeline)
        self.bus.post(eos_message)
        return False  # Stop the idle_add callback


def verify_rtsp_stream(rtsp_url):
    Gst.init(None)
    running = True
    pipeline_str = f'rtspsrc location={rtsp_url} ! watchdog timeout=5000 ! fakesink'

    pipeline = Gst.parse_launch(pipeline_str)
    bus = pipeline.get_bus()


    # Start the pipeline
    pipeline.set_state(Gst.State.PLAYING)
    t0 = time.time()

    while True:
        if (time.time() - t0) > 8:
            break
        message = bus.timed_pop_filtered(10000, Gst.MessageType.ANY)

        time.sleep(0.02)
        if message:
            # print('{}:{}'.format(self.cam_idx,message.type))
            if message.type == Gst.MessageType.ERROR:
                err, debug = message.parse_error()

                print(
                    "Received from element {}: {}".format(
                            message.src.get_name(), err
                    )
                )
                print(
                    "Debugging information: {}".format(
                            debug
                    )
                )
                print(
                    " End-Of-Stream reached."
                )
                running = False
                break
            elif message.type == Gst.MessageType.EOS:
                print(
                    "EOS"
                )
                running = False
                break
            elif message.type == Gst.MessageType.STATE_CHANGED:
                if isinstance(message.src, Gst.Pipeline):
                    (
                        old_state,
                        new_state,
                        pending_state,
                    ) = message.parse_state_changed()

                    print(
                        " Pipeline state changed from {} to {}.".format(
                            old_state.value_nick,
                            new_state.value_nick,
                        )
                    )


    # Stop the pipeline
    pipeline.set_state(Gst.State.NULL)
    print("################ Video is running ######################## :{}".format(running))
    return running



class StreamServer:
    def __init__(self,decoders = {},url_pattern="/video",port=8554,):
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        self.decoders = decoders
        self.url_pattern = url_pattern
        self.port = port
        Gst.init(None)
        self.mainloop = GLib.MainLoop()
        self.server = GstRtspServer.RTSPServer()
        self.server.set_service(str(self.port))
        self.mounts = self.server.get_mount_points()
        self.factory_paths = set()


        self.context_id = 0
        self.running = False
        self.stayAwake = True

        GLib.threads_init()
        log.info("StreamServer initialized")

    def exit_gracefully(self, signum, frame):
        self.stop()
        self.stayAwake = False


    def launch(self):
        for decoder in self.decoders.values():
            print("Waiting for the portnumber from internal pipeline")
            success,cam_idx,udp_port = decoder.get_unique_udpsink_port()
            factory = GstRtspServer.RTSPMediaFactory()
            # Factory must be shared to allow multiple connections
            factory.set_shared(True)

            launch_str ='( udpsrc name=pay0 port={} buffer-size=524288 caps="application/x-rtp, media=video, clock-rate=90000, encoding-name=(string)H264, payload=96 " )'.format(udp_port)
            log.debug(launch_str)
            cam_mutex.acquire()
            try:

                factory.set_launch(launch_str)
                url_path = self.url_pattern+str(cam_idx)
                self.factory_paths.add(url_path)
                self.mounts.add_factory(url_path, factory)
                self.context_id = self.server.attach(None)

            # mainloop.run()
                self.mainthread = Thread(target=self.mainloop.run)
                self.mainthread.daemon = True
                self.mainthread.start()
                self.running = True
            finally:
                cam_mutex.release()
            log.info("Running RTSP Server")

    def start(self):
        # while True:
        #     print("Sleeping for 10 secs")
        #     time.sleep(10)
        for decoder in self.decoders.values():
            success,cam_idx,udp_port = decoder.get_unique_udpsink_port()
            url_path = f"rtsp://127.0.0.1:{self.port}"+self.url_pattern+str(cam_idx)
            print(f"Verifying RTSP connection for {url_path}")
            running = verify_rtsp_stream(url_path)
            if not running:
                self.restart()
                break

    def disconnect_all(self, a, b):
        return GstRtspServer.RTSPFilterResult.REMOVE

    def stop(self):
        if self.running:
            print("Suspending server")
            log.debug("Suspending RTSP Server")
            cam_mutex.acquire()
            try:
                print(self.context_id)
                print(self.server.client_filter(self.disconnect_all))
                time.sleep(0.3)
                self.mainloop.quit()
                self.mainthread.join()
                for path in self.factory_paths:
                    self.mounts.remove_factory(path)
                GLib.Source.remove(self.context_id)
                self.running = False
            finally:
                cam_mutex.release()

    def restart(self):
        # TODO: Manipulate the running pipe rather than destroying and recreating it.
        self.stop()
        self.launch()


class Decoder:

    def __init__(self,cam_idx,udp_port):
        self.cam_idx = cam_idx
        self.udp_port = udp_port

    def get_unique_udpsink_port(self):
        return True,self.cam_idx,self.udp_port
    

if __name__ == '__main__':
    # loaderscreen = LoaderScreen()
    # loaderscreen.start()
    streamServer = StreamServer({1:Decoder(0,15001),2:Decoder(1,15002)})
    streamServer.launch()
    # streamServer.start()
    time.sleep(30)
    print("stopping")
    # loaderscreen.stop()
    print("Finished")
    while True:
        time.sleep(100)