import sys
from ctypes import *
import time
import gi
import cv2
from multiprocessing.managers import SharedMemoryManager
import multiprocessing as mp
gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GstRtspServer, GLib, GObject
import numpy as np 
import threading
import multiprocessing
import logging
Gst.init(None)
import traceback



def on_debug(category, level, dfile, dfctn, dline, source, message, user_data):
    if source:
        logging.info('Debug {}: {}'.format(
            Gst.DebugLevel.get_name(level), message.get()))
    else:
        logging.info('Debug {}: {}'.format(
            Gst.DebugLevel.get_name(level), message.get()))


def set_gst_logger(enable=False , verbosity=None):
    result = True
    try:
        if enable:
            Gst.debug_set_active(True)
            if verbosity and isinstance(verbosity, int) and (verbosity in range(0,10)):
                Gst.debug_set_default_threshold(verbosity)
            else:
                result = False
                logging.error("GST verbosity allowed to be in 0-6")

            Gst.debug_add_log_function(on_debug, None)
            Gst.debug_remove_log_function(Gst.debug_log_default)

        else:
            Gst.debug_set_active(False)
            
    
    except Exception as e:
        result = False

    return result


class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self,udp_port,codec, properties={}):
        super(SensorFactory, self).__init__(**properties)
        self.udp_port = udp_port
        self.codec = codec
        logging.info("sensory factory")

        self.launch_string = (
                '( udpsrc name=pay0 port=%d buffer-size=524288 caps="application/x-rtp, media=video, clock-rate=90000, encoding-name=(string)%s, payload=96 " )'
            % (self.udp_port, self.codec)
        )




    

    def do_create_element(self, url):
        request_uri = url.get_request_uri()
        logging.info('[INFO]: stream request on {}'.format(request_uri))
        return Gst.parse_launch(self.launch_string)

    def do_configure(self, rtsp_media):
        self.rtsp_media = rtsp_media
        rtsp_media.set_reusable(True)
        # self.appsrc = rtsp_media.get_element().get_child_by_name('pay0')
        




class Decoder(multiprocessing.Process):

    def __init__(self, location,resolution,cam_idx, portnum, gie='nvinfer', codec='H264', bitrate=4000000,udp_port=5400):
        super().__init__()
        self.location = location
        self.gie = gie
        self.codec = codec
        self.bitrate = bitrate
        self.cam_idx = cam_idx
        self.portnum = portnum
        self.udp_port = udp_port

        self.width = resolution[0] if resolution else None
        self.height = resolution[1] if resolution else None
        self.stop_event = multiprocessing.Event()
        self.is_dead_event = multiprocessing.Event()
        self.new_frame_ready = multiprocessing.Event()
        self.overlay_queue = multiprocessing.Queue()
        self.overlay_queue_kill_event = multiprocessing.Event()
        self.gstoverlay = None
        # Glib loop for encoder pipeline to keep alive
        self.gloop = GLib.MainLoop()
        self.gloop_thread = threading.Thread(target=self.gloop.run)
        self.gloop_thread.daemon = True


    def get_new_frame_ready(self):
        return self.new_frame_ready
    
    def get_stop_event(self):
        return self.stop_event
    
    def get_overlay_queue(self):
        return self.overlay_queue

    def get_overlay_queue_kill_event(self):
        return self.overlay_queue_kill_event
    
    def run(self):
        self.pipeline = None
        try:
            self.gloop_thread.start()
        except BaseException as e:
            traceback.print_exc()

        # Create and launch the pipeline and main loop
        result = self.launch_pipeline()
        print(
            "\n\t*** [D-{}] DeepStream: Launched RTSP Streaming at rtsp://localhost:{}/video{} ***\n\n".format(self.cam_idx, self.portnum, self.cam_idx)
        )

        rtsp_port_num = self.portnum
        self.server = GstRtspServer.RTSPServer.new()
        self.server.props.service = "%d" % rtsp_port_num
        self.server.attach(None)

        self.factory = SensorFactory(codec=self.codec,udp_port=self.udp_port)
        # self.factory.set_launch(
        #     '( udpsrc name=pay0 port=%d buffer-size=524288 caps="application/x-rtp, media=video, clock-rate=90000, encoding-name=(string)%s, payload=96 " )'
        #     % (self.udp_port, self.codec)
        # )
        self.factory.set_shared(True)
        self.server.get_mount_points().add_factory("/video"+self.cam_idx, self.factory)

        # start play back and listen to events
        print("[D-{}] Starting pipeline soon....\n".format(self.cam_idx))

##################################
        # while True:
        #     time.sleep(30)
        #     print("D{} is sleeping for 30s",format(self.cam_idx))



#################################



        # Keep live main loop
        no_of_recovery  = 0
        while True:
            if not self.stop_event.is_set():
                number_of_tries = 0
                status, state, pending = self.pipeline.get_state(0)
                
                print("(D{}) Number_of_tries:{}".format(self.cam_idx,str(number_of_tries)))
                if state == Gst.State.PAUSED:
                    time.sleep(1)
                    number_of_tries = number_of_tries + 1
                    # logging.info(state)
                else:                    
                    print('(D{}) Source is UP now - {}'.format(self.cam_idx, self.location))

                while True:
                    message = self.bus.timed_pop_filtered(10000, Gst.MessageType.ANY)

                    time.sleep(0.02)
                    if message:
                        if message.type == Gst.MessageType.ERROR:
                            err, debug = message.parse_error()
                            
                            print("({}) Received from element {}: {}".format(self.cam_idx, message.src.get_name(), err))
                            print("({}) Debugging information: %s".format(self.cam_idx,debug))
                            print("({}) End-Of-Stream reached.".format(self.cam_idx))

                            self.err = 1
                            self.launch_pipeline()
                        elif message.type == Gst.MessageType.EOS:
                            
                            print("({}) End-Of-Stream reached.".format(self.cam_idx))
                            self.err = 1
                            self.launch_pipeline()
                        elif message.type == Gst.MessageType.STATE_CHANGED:
                            if isinstance(message.src, Gst.Pipeline):
                                old_state, new_state, pending_state = message.parse_state_changed()
                                
                                print("({}) Pipeline state changed from {} to {}.".format(self.cam_idx, old_state.value_nick, new_state.value_nick))
                    
                    status, state, pending = self.pipeline.get_state(0)
                    if state == Gst.State.PAUSED or state == Gst.State.NULL:
                        print("(D{}) Pipeline is not running, seeing its state as paused or NULL".format(self.cam_idx))
                        self.launch_pipeline()
            else:
                break

        # Cleanup the resources
        self.pipeline.set_state(Gst.State.NULL)
        self.gloop.quit()
        del self.pipeline
        del self.bus
        del self.gloop

        # Wait to finish the main loop
        self.gloop_thread.join()
        
        self.is_dead_event.set()    
        print("[D-{}] FREED ALL RESOURCES !\n".format(self.cam_idx))


    


    def launch_pipeline(self,):
        '''
            Configuring the all necessary plugins and setting up and launching the pipeline.
            Run the glib main loop thread to make the process alive

        '''

        Gst.init(None)
        if self.pipeline:
            self.pipeline.set_state( Gst.State.PAUSED)
            time.sleep(.1)
            self.pipeline.set_state( Gst.State.NULL)
            time.sleep(.1)
            self.server.get_mount_points().remove_factory("/video"+self.cam_idx)
            print("Removed mounts on DE-{}".format(self.cam_idx))
            time.sleep(.1)
            self.server.get_mount_points().add_factory("/video"+self.cam_idx, self.factory)
            time.sleep(.1)
        

        self.pipeline = Gst.parse_launch('filesrc location={} ! qtdemux ! h264parse ! avdec_h264 \
                              ! videoconvert ! tee name=t ! queue ! autovideosink t. ! x264enc speed-preset=slower subme=10 tune=zerolatency bitrate=2000 ! rtph264pay ! udpsink name=udpsink'.format(self.location,',width='+str(self.width)+',height='+str(self.height) if self.width and self.height else ''))
        
        sink = self.pipeline.get_by_name('udpsink')
        if not sink:
            sys.stderr.write("Unable to create udpsink")
        sink.set_property("host", "224.224.255.255")
        sink.set_property("port", self.udp_port)
        sink.set_property("async", False)
        sink.set_property("sync", 1)
        sink.set_property("qos", 0)

        # Gstreamer bus to handle mesages
        self.bus = self.pipeline.get_bus()


        self.pipeline.set_state(Gst.State.PLAYING)

        # Let the process take some time establish the connection before giving the feedback to end user.
        time.sleep(3)
    
        return True

    

    def stop_stream(self):
         self.stop_event.set()
         return True
    

    def is_dead(self):
        return self.is_dead_event.is_set()


FILE_LOGGER =logger = logging.getLogger('my_logger')
TERMINAL_LOGGER = logging.getLogger('my_logger')
DEFAULT_RESOLUTION = (1920, 1080)
DEFAULT_FPS = 30
class DecoderEncoder():

    self_incrementing_port_number = 3000
    def __init__(self, Address, index, resolution=DEFAULT_RESOLUTION, fps=DEFAULT_FPS,port=8554, terminal_on = False, file_logs = True):
        DecoderEncoder.self_incrementing_port_number+=1
        self.udp_unique_port = DecoderEncoder.self_incrementing_port_number
        self.TF_ON = False
        self.terminal_on = terminal_on
        self.file_logs = file_logs
        self.is_local = False
        self.port = port

        
        if isinstance(resolution, tuple) and len(resolution) == 2 and all(isinstance(no, (int, float)) for no in resolution):
            self.resolution = resolution
        else:
            self.resolution = DEFAULT_RESOLUTION
            
        
        if isinstance(fps, (int, float)):
            self.framerate = fps
        else:
            self.framerate = DEFAULT_FPS
            

        self.gst_decoder = 'NOT LIVE'
        self.Cam_idx = str(index)
        self.Last_Frame = (np.zeros((self.resolution[1], self.resolution[0], 3)).astype(np.uint8), [], 0, time.ctime())
        self.Last_Frame32 = (np.zeros((self.resolution[1], self.resolution[0], 3)).astype(np.float32), [], 0, time.ctime())
        self.Last_Frame[0][:] = 100
        self.Last_Frame32[0][:] = 100
        self.empty_frame = cv2.putText(self.Last_Frame[0], "No Frames available, Retrying...", (400, 350), cv2.FONT_HERSHEY_SIMPLEX, 2,
                            (0, 0, 255), 2)

        
        self.Time_of_Last_Frame = None
        # Current Cam
        self.camProcess = None
        self.camlink = Address
        self.pixel_array = np.zeros((self.resolution[1], self.resolution[0], 3)).astype(np.uint8)

        self.init_frame_time = time.time()
        self.frames_sended = 0
        self.get_frame_call_timestamp = None

        self.terminate = 0
        self.Thermal = 1
        self.stop = None
        self.pause_event = None
        self.decoder = Decoder(location=self.camlink,resolution=resolution, cam_idx =self.Cam_idx, portnum=self.port,udp_port=self.udp_unique_port)
        self.decoder.start()


        
          
if __name__ == '__main__':
    # set_gst_logger(True,3)
    de_obj = DecoderEncoder(Address='/home/ajith/Downloads/dance.mp4',index=1,port=9000)
    while True:
        print("Encoder is working")
        time.sleep(40)

